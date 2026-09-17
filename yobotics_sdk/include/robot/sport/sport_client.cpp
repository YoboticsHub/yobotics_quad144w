#include "sport_client.hpp"
#include "sport_api.hpp"
#include "channel_publisher.hpp"
#include <cstdlib>
#include <string>

namespace yobotics {
namespace robot {

namespace {
enum ApiCode {
    PASSIVE = ROBOT_SPORT_API_ID_PASSIVE,
    DAMP = ROBOT_SPORT_API_ID_DAMP,
    RECOVERY_STAND = ROBOT_SPORT_API_ID_RECOVERY_STAND,
    STAND_DOWN = ROBOT_SPORT_API_ID_STAND_DOWN,
    DEVELOPMENT = ROBOT_SPORT_API_ID_DEVELOPMENT,
    RL_WALK = ROBOT_SPORT_API_ID_RL_WALK
};

void reset_motion_fields(sport_client_cmd_t& cmd) {
    cmd.body_height = 0.0f;
    cmd.step_height = 0.0f;
    cmd.euler_angles[0] = 0.0f;
    cmd.euler_angles[1] = 0.0f;
    cmd.euler_angles[2] = 0.0f;
    cmd.velocity[0] = 0.0f;
    cmd.velocity[1] = 0.0f;
    cmd.velocity[2] = 0.0f;
}

std::string resolve_lcm_url() {
    const char* env = std::getenv("YOBOTICS_LCM_URL");
    if (env && env[0] != '\0') {
        return std::string(env);
    }
    return "udpm://239.255.76.67:7667?ttl=255";
}
}  // namespace

static lcm::LCM sport_client_lcm(resolve_lcm_url());
static sport_client_cmd_t sport_client_cmd;
static ChannelPublisher sport_publisher(&sport_client_lcm);

SportClient::SportClient() {
    sport_client_cmd.rc_enable = 1;
    reset_motion_fields(sport_client_cmd);
    sport_client_cmd.api = ApiCode::PASSIVE;
}

int32_t SportClient::Passive() {
    sport_client_cmd.api = ApiCode::PASSIVE;
    reset_motion_fields(sport_client_cmd);
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::Damp() {
    sport_client_cmd.api = ApiCode::DAMP;
    reset_motion_fields(sport_client_cmd);
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::RecoveryStand() {
    sport_client_cmd.api = ApiCode::RECOVERY_STAND;
    reset_motion_fields(sport_client_cmd);
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::StandDown() {
    sport_client_cmd.api = ApiCode::STAND_DOWN;
    reset_motion_fields(sport_client_cmd);
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::Development() {
    sport_client_cmd.api = ApiCode::DEVELOPMENT;
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::RLWalk() {
    sport_client_cmd.api = ApiCode::RL_WALK;
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::SetRCEnable(bool enable) {
    sport_client_cmd.rc_enable = enable ? 1 : 0;
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::EnableLCMControl() {
    return SetRCEnable(true);
}

int32_t SportClient::DisableLCMControl() {
    return SetRCEnable(false);
}

int32_t SportClient::Move(float vx, float vy, float vyaw) {
    sport_client_cmd.velocity[0] = vx;
    sport_client_cmd.velocity[1] = vy;
    sport_client_cmd.velocity[2] = vyaw;
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::BodyHeight(float body_height) {
    if (body_height > 0.20f) {
        body_height = 0.20f;
    } else if (body_height < -1.00f) {
        body_height = -1.00f;
    }
    sport_client_cmd.body_height = body_height;
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

int32_t SportClient::Euler(float roll_cmd, float pitch_cmd) {
    if (roll_cmd > 0.50f) {
        roll_cmd = 0.50f;
    } else if (roll_cmd < -0.50f) {
        roll_cmd = -0.50f;
    }

    if (pitch_cmd > 0.50f) {
        pitch_cmd = 0.50f;
    } else if (pitch_cmd < -0.50f) {
        pitch_cmd = -0.50f;
    }

    // rt_lcm.cpp maps euler_angles[1] -> omega_des[0] and euler_angles[2] -> omega_des[1].
    sport_client_cmd.euler_angles[1] = roll_cmd;
    sport_client_cmd.euler_angles[2] = pitch_cmd;
    sport_publisher.write(&sport_client_cmd);
    return 0;
}

}  // namespace robot
}  // namespace yobotics
