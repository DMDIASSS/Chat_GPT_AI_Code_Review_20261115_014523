#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <RLGymCPP/Gamestates/GameState.h>
#include <RLGymCPP/Gamestates/StateUtil.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <RLGymCPP/CommonValues.h>
#include <RLGymCPP/ThreadPool.h>

#include <Sim/Arena/Arena.h>
#include <Sim/Car/Car.h>
#include <Sim/Ball/Ball.h>
#include <Sim/BallPredTracker/BallPredTracker.h>

#include <vector>
#include <memory>
#include <cmath>
#include <algorithm>
#include <random>
#include <iostream>

namespace py = pybind11;
using namespace RLGC;

namespace Zenith {

inline bool IsChronosMirror(const Player& p) {
    return InvertPhys(p, p.team == Team::ORANGE).pos.x > 0;
}

struct TeacherObsHelper {
    static void PlayerObs(std::vector<float>& out, const Player& p, bool inv, bool mirror, const PhysState& ball) {
        auto phys = MirrorPhysX(InvertPhys(p, inv), mirror);
        auto pushVec = [&](const Vec& v, float scale) {
            out.push_back(v.x * scale); out.push_back(v.y * scale); out.push_back(v.z * scale);
        };
        pushVec(phys.pos, 1.f / 5000.f);
        pushVec(phys.rotMat.forward, 1.f);
        pushVec(phys.rotMat.up, 1.f);
        pushVec(phys.vel, 1.f / 2300.f);
        pushVec(phys.angVel, 1.f / 3.f);
        pushVec(phys.rotMat.Dot(phys.angVel), 1.f / 3.f);
        pushVec(phys.rotMat.Dot(ball.pos - phys.pos), 1.f / 5000.f);
        pushVec(phys.rotMat.Dot(ball.vel - phys.vel), 1.f / 2300.f);
        out.push_back(p.boost / 100.f);
        out.push_back(p.isOnGround ? 1.f : 0.f);
        out.push_back(p.HasFlipOrJump() ? 1.f : 0.f);
        out.push_back(p.isDemoed ? 1.f : 0.f);
        out.push_back(p.hasJumped ? 1.f : 0.f);
    }

    static std::vector<float> BuildChronos(const Player& p, const GameState& s) {
        std::vector<float> out;
        out.reserve(225);
        bool inv = p.team == Team::ORANGE;
        bool mirror = IsChronosMirror(p);
        auto ball = MirrorPhysX(InvertPhys(s.ball, inv), mirror);
        auto pushVec = [&](const Vec& v, float scale) {
            out.push_back(v.x * scale); out.push_back(v.y * scale); out.push_back(v.z * scale);
        };
        pushVec(ball.pos, 1.f / 5000.f);
        pushVec(ball.vel, 1.f / 2300.f);
        pushVec(ball.angVel, 1.f / 3.f);
        Action prev = p.prevAction;
        if (mirror) { prev.steer = -prev.steer; prev.yaw = -prev.yaw; prev.roll = -prev.roll; }
        for (float x : prev) out.push_back(x);

        const auto& pads = s.GetBoostPads(inv);
        const auto& timers = s.GetBoostPadTimers(!inv);
        for (int i = 0; i < 34; i++) {
            int idx = i;
            if (mirror) {
                auto v = CommonValues::BOOST_LOCATIONS[i];
                for (int j = 0; j < 34; j++) {
                    auto b = CommonValues::BOOST_LOCATIONS[j];
                    if (std::abs(b.x + v.x) < 3 && std::abs(b.y - v.y) < 3) { idx = j; break; }
                }
            }
            out.push_back(pads[idx] ? 1.f : 1.f / (1.f + timers[idx]));
        }

        PlayerObs(out, p, inv, mirror, ball);
        out.insert(out.end(), 58, 0.f);
        std::vector<float> other;
        for (const auto& x : s.players) {
            if (x.carId != p.carId) PlayerObs(other, x, inv, mirror, ball);
        }
        out.insert(out.end(), other.begin(), other.end());
        out.insert(out.end(), 58, 0.f);
        return out;
    }

    static std::vector<float> BuildGalactus(const Player& p, const GameState& s, BallPredTracker* tracker) {
        std::vector<float> out;
        out.reserve(258);
        bool inv = p.team == Team::ORANGE;
        bool mirror = false;
        auto ball = InvertPhys(s.ball, inv);
        auto pushVec = [&](const Vec& v, float scale) {
            out.push_back(v.x * scale); out.push_back(v.y * scale); out.push_back(v.z * scale);
        };
        pushVec(ball.pos, 1.f / 5000.f);
        pushVec(ball.vel, 1.f / 2300.f);
        pushVec(ball.angVel, 1.f / 3.f);
        for (float x : p.prevAction) out.push_back(x);

        const auto& pads = s.GetBoostPads(inv);
        const auto& timers = s.GetBoostPadTimers(inv);
        for (int i = 0; i < 34; i++) {
            out.push_back(pads[i] ? 1.f : 1.f / (1.f + timers[i]));
        }

        auto ownPos = InvertPhys(p, inv).pos;
        Vec relative = {};
        float bestDist = 1500.f * 1500.f;
        for (int i : {3, 4, 15, 18, 29, 30}) {
            auto delta = CommonValues::BOOST_LOCATIONS[i] - ownPos;
            float d = delta.x * delta.x + delta.y * delta.y;
            if (pads[i] && d <= bestDist) { bestDist = d; relative = delta; }
        }
        pushVec(relative, 1.f / 5000.f);

        PlayerObs(out, p, inv, mirror, ball);
        out.insert(out.end(), 58, 0.f);
        std::vector<float> other;
        for (const auto& x : s.players) {
            if (x.carId != p.carId) PlayerObs(other, x, inv, mirror, ball);
        }
        out.insert(out.end(), other.begin(), other.end());
        out.insert(out.end(), 58, 0.f);

        if (tracker) {
            tracker->UpdatePredFromArena(s.lastArena);
            for (int t : {30, 60, 120, 180, 240}) {
                auto phys = InvertPhys(tracker->predData.at(t), inv);
                pushVec(phys.pos, 1.f / 5000.f);
                pushVec(phys.vel, 1.f / 2300.f);
            }
        } else {
            out.insert(out.end(), 30, 0.f);
        }
        return out;
    }
};

class ArenaWrapper {
public:
    Arena* arena;
    GameState state;
    GameState prevState;
    std::unique_ptr<BallPredTracker> ballTracker;
    DefaultAction actionParser;
    std::mt19937 rng;
    uint32_t stepCount = 0;
    int currentScenario = 0;

    ArenaWrapper(unsigned seed, const std::string& car0Hitbox = "breakout", const std::string& car1Hitbox = "octane")
        : rng(seed) {
        arena = Arena::Create(GameMode::SOCCAR);
        auto config0 = (car0Hitbox == "breakout") ? CAR_CONFIG_BREAKOUT : CAR_CONFIG_OCTANE;
        auto config1 = (car1Hitbox == "breakout") ? CAR_CONFIG_BREAKOUT : CAR_CONFIG_OCTANE;
        arena->AddCar(Team::BLUE, config0);
        arena->AddCar(Team::ORANGE, config1);
        ballTracker = std::make_unique<BallPredTracker>(arena, 273);
        ResetToScenario(0);
    }

    ~ArenaWrapper() {
        if (arena) delete arena;
    }

    void ResetToScenario(int scen) {
        currentScenario = scen;
        stepCount = 0;
        arena->ResetToRandomKickoff();
        auto unif = [&](float a, float b) { return std::uniform_real_distribution<float>(a, b)(rng); };

        auto cars = arena->GetCars();
        Car* blueCar = nullptr;
        Car* orangeCar = nullptr;
        for (Car* c : cars) {
            if (c->team == Team::BLUE) blueCar = c;
            else orangeCar = c;
        }

        switch (scen) {
            case 1: { // High Aerial Threat (Prejump Required)
                BallState bs = {};
                float bx = unif(-600.f, 600.f);
                float by = unif(600.f, 1800.f);
                bs.pos = Vec(bx, by, unif(120.f, 400.f));
                Vec targetGoal = Vec(unif(-750.f, 750.f), -5140.f, unif(1400.f, 1950.f));
                Vec shotDir = (targetGoal - bs.pos).Normalized();
                float shotSpeed = unif(1600.f, 2050.f);
                bs.vel = shotDir * shotSpeed;
                arena->ball->SetState(bs);

                CarState defCs = {};
                defCs.pos = Vec(unif(-400.f, 400.f), -4950.f, 17.f);
                defCs.rotMat = Angle(float(M_PI / 2), 0.f, 0.f).ToRotMat();
                defCs.boost = unif(45.f, 95.f);
                blueCar->SetState(defCs);

                CarState oppCs = {};
                oppCs.pos = bs.pos + shotDir * 200.f; oppCs.pos.z = 17.f;
                oppCs.rotMat = Angle(-float(M_PI / 2), 0.f, 0.f).ToRotMat();
                oppCs.boost = unif(30.f, 60.f);
                orangeCar->SetState(oppCs);
                break;
            }
            case 2: { // Fake Challenge / Low Cut
                BallState bs = {};
                float bx = unif(-700.f, 700.f);
                float by = unif(600.f, 1800.f);
                bs.pos = Vec(bx, by, 93.f);
                bs.vel = Vec(unif(-250.f, 250.f), -unif(700.f, 1100.f), 0.f);
                arena->ball->SetState(bs);

                CarState defCs = {};
                defCs.pos = Vec(unif(-500.f, 500.f), -4700.f, 17.f);
                defCs.rotMat = Angle(float(M_PI / 2), 0.f, 0.f).ToRotMat();
                defCs.boost = unif(40.f, 80.f);
                blueCar->SetState(defCs);

                CarState oppCs = {};
                oppCs.pos = Vec(bx, by + 180.f, 17.f);
                oppCs.vel = bs.vel;
                oppCs.rotMat = Angle(-float(M_PI / 2), 0.f, 0.f).ToRotMat();
                oppCs.boost = unif(50.f, 90.f);
                orangeCar->SetState(oppCs);
                break;
            }
            case 3: { // Shadow Defense / Retreat
                BallState bs = {};
                float bx = unif(400.f, 2000.f) * (unif(0.f, 1.f) > 0.5f ? 1.f : -1.f);
                float by = unif(-800.f, 1500.f);
                bs.pos = Vec(bx, by, unif(93.f, 180.f));
                bs.vel = Vec(-bx * 0.1f, -unif(600.f, 1100.f), 0.f);
                arena->ball->SetState(bs);

                CarState defCs = {};
                defCs.pos = Vec(bx - (bx > 0 ? 600.f : -600.f), by - 800.f, 17.f);
                defCs.vel = Vec(0.f, -unif(700.f, 1200.f), 0.f);
                defCs.rotMat = Angle(-float(M_PI / 2), 0.f, 0.f).ToRotMat();
                defCs.boost = unif(25.f, 60.f);
                blueCar->SetState(defCs);

                CarState oppCs = {};
                oppCs.pos = Vec(bx, by + 220.f, 17.f);
                oppCs.vel = bs.vel;
                oppCs.rotMat = Angle(-float(M_PI / 2), 0.f, 0.f).ToRotMat();
                oppCs.boost = unif(40.f, 80.f);
                orangeCar->SetState(oppCs);
                break;
            }
            case 4: { // Arsenal Flip Reset Musty Setup
                BallState bs = {};
                float sideSign = (unif(0.f, 1.f) > 0.5f ? 1.f : -1.f);
                bs.pos = Vec(sideSign * unif(2200.f, 3200.f), unif(-1000.f, 1000.f), unif(650.f, 1100.f));
                bs.vel = Vec(-sideSign * unif(500.f, 900.f), unif(600.f, 1200.f), unif(300.f, 650.f));
                arena->ball->SetState(bs);

                CarState atkCs = {};
                atkCs.pos = bs.pos - bs.vel.Normalized() * unif(120.f, 240.f);
                atkCs.pos.z = std::max(100.f, atkCs.pos.z - 80.f);
                atkCs.vel = bs.vel * unif(0.9f, 1.05f);
                Angle atkAngle = Angle(std::atan2(bs.vel.y, bs.vel.x), -0.4f, float(M_PI)); // inverted
                atkCs.rotMat = atkAngle.ToRotMat();
                atkCs.isOnGround = false;
                atkCs.hasJumped = true;
                atkCs.hasDoubleJumped = true;
                atkCs.boost = unif(70.f, 100.f);
                blueCar->SetState(atkCs);

                CarState defCs = {};
                defCs.pos = Vec(unif(-600.f, 600.f), 4900.f, 17.f);
                defCs.rotMat = Angle(-float(M_PI / 2), 0.f, 0.f).ToRotMat();
                defCs.boost = unif(40.f, 80.f);
                orangeCar->SetState(defCs);
                break;
            }
            default:
                break;
        }

        std::vector<Action> zeroActions = { Action{}, Action{} };
        state.UpdateFromArena(arena, zeroActions, nullptr);
        prevState = state;
    }
};

class ZenithArenaPool {
public:
    int numArenas;
    int tickSkip;
    int actionDelay;
    std::vector<std::unique_ptr<ArenaWrapper>> wrappers;
    DefaultAction actionParser;
    std::array<int, 90> mirrorMap;

    ZenithArenaPool(int nArenas, int tSkip, int aDelay, const std::string& meshDir, unsigned baseSeed,
                    const std::string& car0Hitbox = "breakout", const std::string& car1Hitbox = "octane")
        : numArenas(nArenas), tickSkip(tSkip), actionDelay(aDelay) {
        RocketSim::Init(meshDir.c_str());
        wrappers.reserve(numArenas);
        for (int i = 0; i < numArenas; i++) {
            wrappers.push_back(std::make_unique<ArenaWrapper>(baseSeed + i * 104729u, car0Hitbox, car1Hitbox));
        }

        for (int i = 0; i < 90; i++) {
            Action a = actionParser.actions[i];
            float targetSteer = -a.steer;
            float targetYaw = -a.yaw;
            float targetRoll = -a.roll;
            int bestMatch = i;
            float bestDist = 1e9f;
            for (int j = 0; j < 90; j++) {
                Action b = actionParser.actions[j];
                if (b.jump == a.jump && b.boost == a.boost && b.handbrake == a.handbrake &&
                    std::abs(b.throttle - a.throttle) < 1e-3f &&
                    std::abs(b.pitch - a.pitch) < 1e-3f) {
                    float d = std::abs(b.steer - targetSteer) + std::abs(b.yaw - targetYaw) + std::abs(b.roll - targetRoll);
                    if (d < bestDist) {
                        bestDist = d;
                        bestMatch = j;
                    }
                }
            }
            mirrorMap[i] = bestMatch;
        }
    }

    // Build Zenith student observation vector (~126 floats)
    std::vector<float> BuildZenithObs(const Player& p, const Player& opp, const GameState& s, BallPredTracker* tracker) {
        std::vector<float> obs;
        obs.reserve(135);
        auto R = p.rotMat;
        auto toLocal = [&](const Vec& v) {
            return Vec(R.forward.Dot(v), R.right.Dot(v), R.up.Dot(v));
        };

        // 1. Local Ball Physics (9 floats)
        Vec relBallPos = toLocal(s.ball.pos - p.pos);
        Vec relBallVel = toLocal(s.ball.vel - p.vel);
        Vec relBallAng = toLocal(s.ball.angVel);
        obs.push_back(relBallPos.x / 5000.f); obs.push_back(relBallPos.y / 5000.f); obs.push_back(relBallPos.z / 5000.f);
        obs.push_back(relBallVel.x / 2300.f); obs.push_back(relBallVel.y / 2300.f); obs.push_back(relBallVel.z / 2300.f);
        obs.push_back(relBallAng.x / 3.f);    obs.push_back(relBallAng.y / 3.f);    obs.push_back(relBallAng.z / 3.f);

        // 2. Self Car World & Local Kinematics (15 floats)
        obs.push_back(p.pos.x / 5000.f); obs.push_back(p.pos.y / 5000.f); obs.push_back(p.pos.z / 2000.f);
        obs.push_back(p.rotMat.forward.x); obs.push_back(p.rotMat.forward.y); obs.push_back(p.rotMat.forward.z);
        obs.push_back(p.rotMat.up.x); obs.push_back(p.rotMat.up.y); obs.push_back(p.rotMat.up.z);
        Vec localCarVel = toLocal(p.vel);
        obs.push_back(localCarVel.x / 2300.f); obs.push_back(localCarVel.y / 2300.f); obs.push_back(localCarVel.z / 2300.f);
        Vec localCarAng = toLocal(p.angVel);
        obs.push_back(localCarAng.x / 5.5f); obs.push_back(localCarAng.y / 5.5f); obs.push_back(localCarAng.z / 5.5f);

        // 3. Self Car Mechanics & Reset State (6 floats)
        obs.push_back(p.boost / 100.f);
        obs.push_back(p.isOnGround ? 1.f : 0.f);
        obs.push_back(p.HasFlipOrJump() ? 1.f : 0.f);
        obs.push_back(p.HasFlipReset() ? 1.f : 0.f);
        obs.push_back(p.isFlipping ? 1.f : 0.f);
        int wheelsInContact = 0;
        for (int w = 0; w < 4; w++) wheelsInContact += p.wheelsWithContact[w];
        obs.push_back(float(wheelsInContact) / 4.f);

        // 4. Previous Control Actions (8 floats)
        for (float a : p.prevAction) obs.push_back(a);

        // 5. Opponent Local Kinematics (13 floats)
        Vec relOppPos = toLocal(opp.pos - p.pos);
        Vec relOppVel = toLocal(opp.vel - p.vel);
        obs.push_back(relOppPos.x / 5000.f); obs.push_back(relOppPos.y / 5000.f); obs.push_back(relOppPos.z / 5000.f);
        obs.push_back(relOppVel.x / 2300.f); obs.push_back(relOppVel.y / 2300.f); obs.push_back(relOppVel.z / 2300.f);
        Vec oppFwdLocal = toLocal(opp.rotMat.forward);
        Vec oppUpLocal = toLocal(opp.rotMat.up);
        obs.push_back(oppFwdLocal.x); obs.push_back(oppFwdLocal.y); obs.push_back(oppFwdLocal.z);
        obs.push_back(oppUpLocal.x); obs.push_back(oppUpLocal.y); obs.push_back(oppUpLocal.z);
        obs.push_back(opp.boost / 100.f);

        // 6. Boost Pad States (34 floats)
        bool inv = (p.team == Team::ORANGE);
        const auto& pads = s.GetBoostPads(inv);
        for (int b = 0; b < 34; b++) obs.push_back(pads[b] ? 1.f : 0.f);

        // 7. Future Ball Prediction Horizon (30 floats)
        if (tracker) {
            tracker->UpdatePredFromArena(s.lastArena);
            for (int t : {12, 30, 60, 96, 144}) { // 0.1s, 0.25s, 0.5s, 0.8s, 1.2s
                auto pred = tracker->predData.at(t);
                Vec pLocal = toLocal(pred.pos - p.pos);
                Vec vLocal = toLocal(pred.vel - p.vel);
                obs.push_back(pLocal.x / 5000.f); obs.push_back(pLocal.y / 5000.f); obs.push_back(pLocal.z / 5000.f);
                obs.push_back(vLocal.x / 2300.f); obs.push_back(vLocal.y / 2300.f); obs.push_back(vLocal.z / 2300.f);
            }
        } else {
            obs.insert(obs.end(), 30, 0.f);
        }

        return obs;
    }

    // Step the entire arena pool
    py::dict Step(py::array_t<int> actionIndices, py::array_t<float> rewardWeights) {
        py::buffer_info actionBuf = actionIndices.request();
        int* actions = static_cast<int*>(actionBuf.ptr);
        int totalPlayers = numArenas * 2;
        if (actionBuf.size != totalPlayers) throw std::runtime_error("Action count mismatch");

        // Reward weights buffer (12 floats)
        py::buffer_info weightBuf = rewardWeights.request();
        float* weights = static_cast<float*>(weightBuf.ptr);

        int obsDim = 115 + 30; // 145 floats
        std::vector<float> allObs(totalPlayers * obsDim);
        std::vector<uint8_t> allMasks(totalPlayers * 90);
        std::vector<float> allRewardComponents(totalPlayers * 12);
        std::vector<float> allScalarRewards(totalPlayers, 0.f);
        std::vector<uint8_t> allTerminals(totalPlayers, 0);

        int goalsBlue = 0, goalsOrange = 0, flipResetsTotal = 0, mustyTotal = 0;

        {
            py::gil_scoped_release release;

            auto stepArena = [&](int arenaIdx) {
                auto& w = wrappers[arenaIdx];
                w->stepCount++;
                w->prevState = w->state;

                // Step action delay
                w->arena->Step(actionDelay);

                // Apply parsed controls
                auto cars = w->arena->GetCars();
                Car* car0 = nullptr;
                Car* car1 = nullptr;
                for (Car* c : cars) {
                    if (c->team == Team::BLUE) car0 = c;
                    else car1 = c;
                }

                Action a0 = actionParser.ParseAction(actions[arenaIdx * 2 + 0], w->state.players[0], w->state);
                Action a1 = actionParser.ParseAction(actions[arenaIdx * 2 + 1], w->state.players[1], w->state);
                car0->controls = (CarControls)a0;
                car1->controls = (CarControls)a1;

                // Step rest of tickSkip
                w->arena->Step(tickSkip - actionDelay);

                std::vector<Action> curActions = { a0, a1 };
                w->state.UpdateFromArena(w->arena, curActions, &w->prevState);

                bool goalScored = w->arena->IsBallScored();
                bool timeout = (w->stepCount >= 1800); // 120 seconds max at 15 Hz
                bool terminal = goalScored || timeout;

                for (int pIdx = 0; pIdx < 2; pIdx++) {
                    int globalIdx = arenaIdx * 2 + pIdx;
                    const auto& p = w->state.players[pIdx];
                    const auto& pPrev = w->prevState.players[pIdx];
                    const auto& opp = w->state.players[1 - pIdx];
                    float dir = (p.team == Team::BLUE) ? 1.f : -1.f;

                    // Compute 12 Decomposed Reward Components
                    float* rComp = &allRewardComponents[globalIdx * 12];
                    std::fill(rComp, rComp + 12, 0.f);

                    // 0: Goal outcome
                    if (goalScored) {
                        bool scored = ((w->state.ball.pos.y > 0) == (p.team == Team::BLUE));
                        rComp[0] = scored ? 10.f : -10.f;
                    }

                    // 1: Ball velocity toward target net
                    rComp[1] = (dir * w->state.ball.vel.y) / 2300.f;

                    // 2: Car closing velocity toward ball
                    Vec toBall = (w->state.ball.pos - p.pos);
                    float dist = toBall.Length();
                    Vec dirBall = dist > 1e-4f ? toBall / dist : Vec(0, 0, 0);
                    rComp[2] = p.vel.Dot(dirBall) / 2300.f;

                    // 3: Car to ball exponential distance
                    rComp[3] = std::exp(-dist / 2500.f);

                    // 4: Ball touch bonus
                    if (p.ballTouchedStep) rComp[4] = 1.0f;

                    // 5: Aerial touch bonus
                    if (p.ballTouchedStep && w->state.ball.pos.z > 300.f) {
                        rComp[5] = 2.0f * (w->state.ball.pos.z / 1000.f);
                    }

                    // 6: 3-Wheel Contact Flip Reset Acquisition
                    int wheels = 0;
                    for (int k = 0; k < 4; k++) wheels += p.wheelsWithContact[k];
                    bool airborne = !p.isOnGround && p.pos.z > 250.f;
                    bool resetAcquired = (wheels >= 3 && p.HasFlipOrJump() && !pPrev.HasFlipOrJump() && dist < 200.f);
                    if (resetAcquired) {
                        rComp[6] = 5.0f;
                    }

                    // 7: Arsenal Musty Flick Discharge
                    bool justFlipped = (p.isFlipping && !pPrev.isFlipping);
                    bool mustyTilted = (p.rotMat.forward.z < -0.4f);
                    bool dodgeBackward = (p.prevAction.pitch > 0.5f);
                    if (justFlipped && mustyTilted && dodgeBackward && p.ballTouchedStep && dir * w->state.ball.vel.y > 800.f) {
                        rComp[7] = 5.0f;
                    }

                    // 8: Defensive Save / Goal Line Interception
                    float prevInward = -dir * w->prevState.ball.vel.y;
                    if (p.ballTouchedStep && dir * w->state.ball.pos.y < -1500.f && prevInward > 400.f && dir * w->state.ball.vel.y > 200.f) {
                        rComp[8] = 5.0f;
                    }

                    // 9: Prejump Liftoff on High Boomer Threat
                    bool incomingHighThreat = (-dir * w->state.ball.vel.y > 900.f && w->state.ball.pos.z > 1200.f && dir * p.pos.y < -3500.f);
                    bool earlyLiftoff = (!p.isOnGround && p.vel.z > 450.f && pPrev.isOnGround);
                    if (incomingHighThreat && earlyLiftoff) {
                        rComp[9] = 3.0f;
                    }

                    // 10: Fake Commit Penalty
                    bool opponentLowFake = (dir * opp.pos.y > -2000.f && w->state.ball.pos.z < 160.f && std::abs(w->state.ball.vel.y) < 600.f);
                    bool unpromptedHighJump = (earlyLiftoff && opponentLowFake && dist > 1200.f);
                    if (unpromptedHighJump) {
                        rComp[10] = -5.0f;
                    }

                    // 11: Boost gain
                    rComp[11] = std::max(0.f, p.boost - pPrev.boost) / 100.f;

                    // Scalar reward via dot product with weights
                    float totalR = 0.f;
                    for (int wIdx = 0; wIdx < 12; wIdx++) totalR += rComp[wIdx] * weights[wIdx];
                    allScalarRewards[globalIdx] = totalR;

                    // Build Zenith student observation
                    auto obsVec = BuildZenithObs(p, opp, w->state, w->ballTracker.get());
                    std::copy(obsVec.begin(), obsVec.end(), &allObs[globalIdx * obsDim]);

                    // Build action mask
                    auto mask = actionParser.GetActionMask(p, w->state);
                    std::copy(mask.begin(), mask.end(), &allMasks[globalIdx * 90]);

                    allTerminals[globalIdx] = terminal ? 1 : 0;
                }

                if (terminal) {
                    if (goalScored) {
                        if (w->state.ball.pos.y > 0) goalsBlue++;
                        else goalsOrange++;
                    }
                    w->ResetToScenario(w->currentScenario);
                }
            };

            for (int i = 0; i < numArenas; i++) stepArena(i);
        }

        // Return numpy arrays to Python
        py::dict result;
        result["obs"] = py::array_t<float>({ totalPlayers, obsDim }, allObs.data());
        result["masks"] = py::array_t<uint8_t>({ totalPlayers, 90 }, allMasks.data());
        result["reward_components"] = py::array_t<float>({ totalPlayers, 12 }, allRewardComponents.data());
        result["rewards"] = py::array_t<float>({ totalPlayers }, allScalarRewards.data());
        result["terminals"] = py::array_t<uint8_t>({ totalPlayers }, allTerminals.data());
        result["goals_blue"] = goalsBlue;
        result["goals_orange"] = goalsOrange;
        return result;
    }

    // Get Teacher Observation for Kickstart Distillation Loss
    py::array_t<float> GetTeacherObs(int arenaIdx, int playerIdx, const std::string& teacherType) {
        if (arenaIdx < 0 || arenaIdx >= numArenas) throw std::runtime_error("Invalid arena index");
        auto& w = wrappers[arenaIdx];
        const auto& p = w->state.players[playerIdx];
        if (teacherType == "chronos") {
            auto obs = TeacherObsHelper::BuildChronos(p, w->state);
            return py::array_t<float>({ 225 }, obs.data());
        } else if (teacherType == "galactus") {
            auto obs = TeacherObsHelper::BuildGalactus(p, w->state, w->ballTracker.get());
            return py::array_t<float>({ 258 }, obs.data());
        }
        throw std::runtime_error("Unknown teacher type: " + teacherType);
    }

    // Get batch of teacher observations for all arenas at once
    py::array_t<float> GetTeacherObsBatch(int playerIdx, const std::string& teacherType) {
        int dim = (teacherType == "chronos") ? 225 : 258;
        std::vector<float> batch(numArenas * dim);
        for (int i = 0; i < numArenas; i++) {
            auto& w = wrappers[i];
            const auto& p = w->state.players[playerIdx];
            std::vector<float> obs;
            if (teacherType == "chronos") {
                obs = TeacherObsHelper::BuildChronos(p, w->state);
            } else {
                obs = TeacherObsHelper::BuildGalactus(p, w->state, w->ballTracker.get());
            }
            std::copy(obs.begin(), obs.end(), &batch[i * dim]);
        }
        return py::array_t<float>({ numArenas, dim }, batch.data());
    }

    py::dict GetCurrentState() {
        int totalPlayers = numArenas * 2;
        int obsDim = 145;
        std::vector<float> allObs(totalPlayers * obsDim);
        std::vector<uint8_t> allMasks(totalPlayers * 90);
        for (int arenaIdx = 0; arenaIdx < numArenas; arenaIdx++) {
            auto& w = wrappers[arenaIdx];
            for (int pIdx = 0; pIdx < 2; pIdx++) {
                int globalIdx = arenaIdx * 2 + pIdx;
                const auto& p = w->state.players[pIdx];
                const auto& opp = w->state.players[1 - pIdx];
                auto obsVec = BuildZenithObs(p, opp, w->state, w->ballTracker.get());
                std::copy(obsVec.begin(), obsVec.end(), &allObs[globalIdx * obsDim]);
                auto mask = actionParser.GetActionMask(p, w->state);
                std::copy(mask.begin(), mask.end(), &allMasks[globalIdx * 90]);
            }
        }
        py::dict res;
        res["obs"] = py::array_t<float>({ totalPlayers, obsDim }, allObs.data());
        res["masks"] = py::array_t<uint8_t>({ totalPlayers, 90 }, allMasks.data());
        return res;
    }

    void SetScenario(int arenaIdx, int scenarioId) {
        if (arenaIdx < 0 || arenaIdx >= numArenas) throw std::runtime_error("Invalid arena index");
        wrappers[arenaIdx]->ResetToScenario(scenarioId);
    }

    py::array_t<int> GetActionMirrorMap() {
        return py::array_t<int>({ 90 }, mirrorMap.data());
    }

    py::array_t<uint8_t> GetTeacherMirrorFlags(int playerIdx) {
        std::vector<uint8_t> flags(numArenas);
        for (int i = 0; i < numArenas; i++) {
            const auto& p = wrappers[i]->state.players[playerIdx];
            flags[i] = IsChronosMirror(p) ? 1 : 0;
        }
        return py::array_t<uint8_t>({ numArenas }, flags.data());
    }

    py::dict ResetAll(int scenarioId = 0) {
        for (int i = 0; i < numArenas; i++) {
            wrappers[i]->ResetToScenario(scenarioId);
        }
        return GetCurrentState();
    }
};

} // namespace Zenith

PYBIND11_MODULE(zenith_sim, m) {
    m.doc() = "Zenith Rocket League high-throughput native multi-arena simulation module";

    py::class_<Zenith::ZenithArenaPool>(m, "ZenithArenaPool")
        .def(py::init<int, int, int, const std::string&, unsigned, const std::string&, const std::string&>(),
             py::arg("num_arenas"),
             py::arg("tick_skip") = 8,
             py::arg("action_delay") = 7,
             py::arg("mesh_dir") = "",
             py::arg("base_seed") = 42,
             py::arg("car0_hitbox") = "breakout",
             py::arg("car1_hitbox") = "octane")
        .def("step", &Zenith::ZenithArenaPool::Step, py::arg("action_indices"), py::arg("reward_weights"))
        .def("get_teacher_obs", &Zenith::ZenithArenaPool::GetTeacherObs, py::arg("arena_idx"), py::arg("player_idx"), py::arg("teacher_type"))
        .def("get_teacher_obs_batch", &Zenith::ZenithArenaPool::GetTeacherObsBatch, py::arg("player_idx"), py::arg("teacher_type"))
        .def("get_action_mirror_map", &Zenith::ZenithArenaPool::GetActionMirrorMap)
        .def("get_teacher_mirror_flags", &Zenith::ZenithArenaPool::GetTeacherMirrorFlags, py::arg("player_idx"))
        .def("get_current_state", &Zenith::ZenithArenaPool::GetCurrentState)
        .def("set_scenario", &Zenith::ZenithArenaPool::SetScenario, py::arg("arena_idx"), py::arg("scenario_id"))
        .def("reset_all", &Zenith::ZenithArenaPool::ResetAll, py::arg("scenario_id") = 0);
}
