#include "channel_subscriber.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

using namespace yobotics::robot;

namespace {
std::string resolve_lcm_url(int argc, char** argv) {
    if (argc > 1 && argv[1] && argv[1][0] != '\0') {
        return std::string(argv[1]);
    }
    const char* env = std::getenv("YOBOTICS_LCM_URL");
    if (env && env[0] != '\0') {
        return std::string(env);
    }
    return "udpm://239.255.76.67:7667?ttl=255";
}
}  // namespace

class RobotStateClient {
public:
    explicit RobotStateClient(const std::string& lcm_url)
        : lcm_(lcm_url), subscriber_(new ChannelSubscriber(&lcm_)) {}
    ~RobotStateClient() { delete subscriber_; }

    void task() {
        subscriber_->read(&quad_state_);
        subscriber_->read(&leg_state_);
        subscriber_->read(&leg_cmd_);

        std::cout << "=== QUAD_ROBOT_STATE_Y20W ===" << std::endl;
        std::cout << "rpy: "
                  << quad_state_.rpy[0] << ", " << quad_state_.rpy[1] << ", "
                  << quad_state_.rpy[2] << std::endl;
        std::cout << "speed(v): " << quad_state_.v << "  height(h): " << quad_state_.h << std::endl;
        std::cout << "state: " << quad_state_.state << "  fault: " << quad_state_.fault << std::endl;

        std::cout << "=== Y20W_QUAD_JOINT_STATE ===" << std::endl;
        std::cout << "joint_q[0..2]: "
                  << leg_state_.joint_q[0] << ", "
                  << leg_state_.joint_q[1] << ", "
                  << leg_state_.joint_q[2] << std::endl;
        std::cout << "joint_qd[0..2]: "
                  << leg_state_.joint_qd[0] << ", "
                  << leg_state_.joint_qd[1] << ", "
                  << leg_state_.joint_qd[2] << std::endl;
        std::cout << "wheel_q[LF, RF, LR, RR]: "
                  << leg_state_.joint_q_supplement[0] << ", "
                  << leg_state_.joint_q_supplement[1] << ", "
                  << leg_state_.joint_q_supplement[2] << ", "
                  << leg_state_.joint_q_supplement[3] << std::endl;

        std::cout << "=== Y20W_QUAD_JOINT_COMMAND ===" << std::endl;
        std::cout << "joint_des_q[0..2]: "
                  << leg_cmd_.joint_des_q[0] << ", "
                  << leg_cmd_.joint_des_q[1] << ", "
                  << leg_cmd_.joint_des_q[2] << std::endl;
        std::cout << "joint_des_kp[0..2]: "
                  << leg_cmd_.joint_des_kp[0] << ", "
                  << leg_cmd_.joint_des_kp[1] << ", "
                  << leg_cmd_.joint_des_kp[2] << std::endl;
        std::cout << "wheel_des_q[LF, RF, LR, RR]: "
                  << leg_cmd_.joint_des_q_supplement[0] << ", "
                  << leg_cmd_.joint_des_q_supplement[1] << ", "
                  << leg_cmd_.joint_des_q_supplement[2] << ", "
                  << leg_cmd_.joint_des_q_supplement[3] << std::endl;

        std::cout << "------------------------------" << std::endl;
    }

private:
    lcm::LCM lcm_;
    ChannelSubscriber* subscriber_{nullptr};
    sport_client_state_t quad_state_{};
    quad_joint_state_t leg_state_{};
    quad_joint_command_t leg_cmd_{};
};

int main(int argc, char** argv) {
    const std::string lcm_url = resolve_lcm_url(argc, argv);
    std::cout << "LCM URL: " << lcm_url << std::endl;

    RobotStateClient client(lcm_url);
    while (true) {
        client.task();
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    return 0;
}
