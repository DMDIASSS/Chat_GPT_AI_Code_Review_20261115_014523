"""Update src/main.cpp, compile GigaForge.exe, and sync native_release.json."""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent
main_cpp = ROOT / "src" / "main.cpp"
s = main_cpp.read_text(encoding="utf8").replace("\r\n", "\n")

old = """ e.actionParser=new GF::Actions(c,otherC,learnerTeam);e.stateSetter=new KickoffState;
 e.terminalConditions={new GoalScoreCondition};
 std::array<float,5> weights={.35f,.1f,0.f,0.f,0.f};
 if(recipe.contains("potential_weights"))weights=recipe["potential_weights"].get<std::array<float,5>>();
 if(recipe.value("mechanics_reward",false)){
  e.rewards={{new GF::MechanicsGoalPotential(recipe.at("gamma"),weights,recipe.value("mechanics_scale",1.f)),1.f}};
 }else{
  e.rewards={{new GF::GoalPotential(recipe.at("gamma"),weights),1.f}};
 }"""

new = """ e.actionParser=new GF::Actions(c,otherC,learnerTeam);
 float defProb=recipe.value("defensive_curriculum_prob",0.f);
 if(defProb>0.f)e.stateSetter=new GF::DefensiveCurriculumStateSetter(defProb,learnerTeam,recipe.at("seed").get<unsigned>()+index*7919u+104729u);
 else e.stateSetter=new KickoffState;
 e.terminalConditions={new GoalScoreCondition};
 std::array<float,5> weights={.35f,.1f,0.f,0.f,0.f};
 if(recipe.contains("potential_weights"))weights=recipe["potential_weights"].get<std::array<float,5>>();
 if(recipe.value("defensive_mechanics_reward",false)){
  e.rewards={{new GF::DefensiveMechanicsGoalPotential(recipe.at("gamma"),weights,recipe.value("mechanics_scale",1.f),recipe.value("defense_scale",1.f)),1.f}};
 }else if(recipe.value("mechanics_reward",false)){
  e.rewards={{new GF::MechanicsGoalPotential(recipe.at("gamma"),weights,recipe.value("mechanics_scale",1.f)),1.f}};
 }else{
  e.rewards={{new GF::GoalPotential(recipe.at("gamma"),weights),1.f}};
 }"""

if old in s:
    s = s.replace(old, new, 1)
    main_cpp.write_text(s, encoding="utf8", newline="\r\n")
    print("Updated src/main.cpp", flush=True)
else:
    assert new in s, "Neither old nor new block found in src/main.cpp"
    print("src/main.cpp already updated", flush=True)

sys.path.insert(0, str(ROOT / "tools"))
import build_native
build_native.build()

exe = ROOT / "native" / "GigaForge.exe"
sha = hashlib.sha256(exe.read_bytes()).hexdigest()
rel_file = ROOT / "native_release.json"
rel = json.loads(rel_file.read_text(encoding="utf8"))
rel["executable_sha256"] = sha
rel_file.write_text(json.dumps(rel, indent=2), encoding="utf8")
print("Synced native_release.json with executable_sha256:", sha, flush=True)

sys.path.insert(0, str(ROOT))
import run as gf_run
subprocess.run([str(exe), "--selftest"], env=gf_run.environment(), check=True)
print("GigaForge.exe --selftest PASSED!", flush=True)
