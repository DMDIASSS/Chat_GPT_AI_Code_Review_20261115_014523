"""
Zenith Teacher Ensemble & Kickstart Distillation
Loads Chronos and Galactus models to provide KL-divergence distillation targets.
"""
from __future__ import annotations

import pathlib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


def _load_sequence(path: pathlib.Path | None, widths: list[int], input_size: int, activation, output: int | None = None) -> nn.Sequential:
    layers = []
    size = input_size
    for width in widths:
        layers.extend([nn.Linear(size, width), nn.LayerNorm(width), activation()])
        size = width
    if output is not None:
        layers.append(nn.Linear(size, output))
    seq = nn.Sequential(*layers)
    if path is not None and path.is_file():
        archive = torch.jit.load(str(path), map_location="cpu")
        seq.load_state_dict(dict(archive.named_parameters()), strict=True)
    seq.requires_grad_(False)
    return seq.eval()


class GigaTeacherNet(nn.Module):
    """
    Direct PyTorch neural network matching GigaLearn TorchScript weights.
    """
    def __init__(self, path: pathlib.Path, kind: str):
        super().__init__()
        self.kind = kind
        if kind == "chronos":
            first = 225
            shared = [960, 960]
            policy = [960, 800, 640, 640]
            act = nn.ReLU
        elif kind == "galactus":
            first = 258
            shared = [1024, 1024]
            policy = [1024] * 4
            act = nn.LeakyReLU
        else:
            raise ValueError(f"Unknown teacher kind: {kind}")

        self.head = _load_sequence(path / "SHARED_HEAD.lt", shared, first, act)
        self.policy = _load_sequence(path / "POLICY.lt", policy, shared[-1], act, 90)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.policy(self.head(x))


class TeacherEnsemble:
    """
    Ensemble manager for Chronos and Galactus teacher distillation.
    """
    DEFAULT_CHRONOS_PATH = pathlib.Path(
        r"E:\Downloads\Chat_GPT_AI\gigaforge\runs\research06\branches\chronos\chronos_winrate_dominance_v1\checkpoints\786432"
    )
    DEFAULT_GALACTUS_PATH = pathlib.Path(
        r"E:\Downloads\Chat_GPT_AI\gigaforge\runs\stationary01\parents\galactus"
    )

    def __init__(
        self,
        chronos_path: pathlib.Path | str | None = None,
        galactus_path: pathlib.Path | str | None = None,
        device: torch.device | str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        self.device = torch.device(device)
        c_path = pathlib.Path(chronos_path) if chronos_path else self.DEFAULT_CHRONOS_PATH
        g_path = pathlib.Path(galactus_path) if galactus_path else self.DEFAULT_GALACTUS_PATH

        print(f"[Teachers] Loading Chronos from {c_path}...")
        self.chronos = GigaTeacherNet(c_path, "chronos").to(self.device).eval()

        print(f"[Teachers] Loading Galactus from {g_path}...")
        self.galactus = GigaTeacherNet(g_path, "galactus").to(self.device).eval()

        # Distillation settings
        self.initial_kd_weight = 0.5
        self.current_kd_weight = 0.5
        self.kd_temperature = 1.0

    def compute_teacher_probs(
        self,
        pool,
        player_idx: int = 0,
        masks: torch.Tensor | None = None
    ) -> torch.Tensor:
        """
        Queries native arena pool for Chronos and Galactus observation batches,
        computes masked teacher logits, un-mirrors Chronos probabilities where appropriate,
        and returns ensemble teacher action probability distribution.
        """
        c_obs_np = pool.get_teacher_obs_batch(player_idx, "chronos")
        g_obs_np = pool.get_teacher_obs_batch(player_idx, "galactus")
        mirror_flags = pool.get_teacher_mirror_flags(player_idx)

        c_obs = torch.from_numpy(c_obs_np).to(self.device)
        g_obs = torch.from_numpy(g_obs_np).to(self.device)

        with torch.inference_mode():
            c_logits = self.chronos(c_obs)
            g_logits = self.galactus(g_obs)

            if masks is not None:
                # Apply mask to teacher logits
                invalid = (masks == 0)
                c_logits = c_logits.masked_fill(invalid, -1e9)
                g_logits = g_logits.masked_fill(invalid, -1e9)

            c_probs = F.softmax(c_logits / self.kd_temperature, dim=-1)
            g_probs = F.softmax(g_logits / self.kd_temperature, dim=-1)

            # Un-mirror Chronos probs where observation was mirrored
            if not hasattr(self, "mirror_map_tensor") or self.mirror_map_tensor is None:
                mirror_map_np = pool.get_action_mirror_map()
                self.mirror_map_tensor = torch.from_numpy(mirror_map_np).long().to(self.device)

            if np.any(mirror_flags):
                mirrored_idx = torch.from_numpy(mirror_flags).bool().to(self.device)
                c_probs[mirrored_idx] = c_probs[mirrored_idx][:, self.mirror_map_tensor]

            # Ensemble target: average probability distribution
            ensemble_probs = 0.5 * (c_probs + g_probs)

            # Strictly enforce zero probability on invalid student actions and re-normalize
            if masks is not None:
                ensemble_probs = ensemble_probs.masked_fill(masks == 0, 0.0)
                prob_sum = ensemble_probs.sum(dim=-1, keepdim=True)
                ensemble_probs = ensemble_probs / torch.clamp(prob_sum, min=1e-8)

            return ensemble_probs

    def compute_kd_loss(
        self,
        student_logits: torch.Tensor,
        teacher_probs: torch.Tensor,
        masks: torch.Tensor | None = None
    ) -> torch.Tensor:
        """
        Computes Kullback-Leibler (KL) divergence loss between student log-probs and teacher probabilities.
        """
        if self.current_kd_weight <= 1e-6:
            return torch.tensor(0.0, device=student_logits.device)

        if masks is not None:
            student_logits = student_logits.masked_fill(masks == 0, -1e9)

        student_log_probs = F.log_softmax(student_logits, dim=-1)
        # KL divergence: sum(teacher_p * (log(teacher_p) - student_log_p))
        # PyTorch F.kl_div with log_target=False takes input=student_log_probs, target=teacher_probs
        kd_loss = F.kl_div(student_log_probs, teacher_probs, reduction="batchmean")
        return self.current_kd_weight * kd_loss

    def anneal_kd_weight(self, student_win_rate_vs_teachers: float):
        """
        Anneals distillation weight as student's win-rate against teachers improves.
        When student reaches 50% win rate, teacher guidance is reduced; above 60%, it turns off.
        """
        if student_win_rate_vs_teachers >= 0.60:
            self.current_kd_weight = 0.0
        elif student_win_rate_vs_teachers >= 0.50:
            factor = (0.60 - student_win_rate_vs_teachers) / 0.10
            self.current_kd_weight = self.initial_kd_weight * factor
        else:
            self.current_kd_weight = self.initial_kd_weight
