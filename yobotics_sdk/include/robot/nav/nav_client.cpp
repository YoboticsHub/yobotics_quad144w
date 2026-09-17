#include "nav_client.hpp"
#include "nav_api.hpp"
#include "channel_publisher.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

namespace yobotics
{
namespace robot
{

namespace {
const char* kDefaultNavLcmUrl = "udpm://239.255.76.67:7667?ttl=255";

std::string resolve_nav_lcm_url() {
    const char* env = std::getenv("YOBOTICS_LCM_URL");
    if (env && env[0] != '\0') {
        return std::string(env);
    }
    return kDefaultNavLcmUrl;
}

const std::string& NavLcmUrl() {
    static const std::string nav_lcm_url = resolve_nav_lcm_url();
    return nav_lcm_url;
}

lcm::LCM& NavLcmInstance() {
    static lcm::LCM nav_lcm(NavLcmUrl());
    return nav_lcm;
}

ChannelPublisher& NavPublisherInstance() {
    static ChannelPublisher publisher(&NavLcmInstance());
    return publisher;
}

control_messages::Command& NavCommandBuffer() {
    static control_messages::Command nav_cmd{};
    return nav_cmd;
}
}

NavClient::NavClient()
    : m_last_response_code(0) {
}

void NavClient::ResetParams() {
    control_messages::Command& cmd = NavCommandBuffer();
    for (int i = 0; i < 9; ++i) {
        cmd.params[i] = 0.0;
    }
    cmd.goal_meta.clear();
}

int32_t NavClient::SendSimpleCode(int32_t code) {
    control_messages::Command& cmd = NavCommandBuffer();
    cmd.cmd = code;
    ResetParams();
    if (!NavLcmInstance().good()) {
        std::cerr << "[NavClient] LCM init failed, lcm_url=" << NavLcmUrl() << std::endl;
        return -1;
    }
    std::cout << "[NavClient] publish cmd=" << code
              << " channel=UPPER_dogNAV_1"
              << " lcm_url=" << NavLcmUrl() << std::endl;
    NavPublisherInstance().writeNav(&cmd);
    return 0;
}

int32_t NavClient::SendCode1801() { return SendSimpleCode(ROBOT_NAV_API_ID_START_MAPPING); }
int32_t NavClient::SendCode1802() { return SendSimpleCode(ROBOT_NAV_API_ID_END_MAPPING); }
int32_t NavClient::SendCode1803() { return SendSimpleCode(ROBOT_NAV_API_ID_START_CUTTER); }
int32_t NavClient::SendCode1804() { return SendSimpleCode(ROBOT_NAV_API_ID_END_CUTTER); }
int32_t NavClient::SendCode1805() { return SendSimpleCode(ROBOT_NAV_API_ID_START_LOCALIZATION); }
int32_t NavClient::SendCode1806() { return SendSimpleCode(ROBOT_NAV_API_ID_END_LOCALIZATION); }
int32_t NavClient::SendCode1807() { return SendSimpleCode(ROBOT_NAV_API_ID_START_NAV); }
int32_t NavClient::SendCode1808() { return SendSimpleCode(ROBOT_NAV_API_ID_END_NAV); }
int32_t NavClient::SendCode1800() { return SendSimpleCode(ROBOT_NAV_API_ID_END_GOAL_PROGRAM); }
int32_t NavClient::SendCode1809() { return SendSimpleCode(ROBOT_NAV_API_ID_START_GOAL_PROGRAM); }
int32_t NavClient::SendCode1820() { return SendSimpleCode(ROBOT_NAV_API_ID_CLEAR_GOAL); }
int32_t NavClient::SendCode1823() { return SendSimpleCode(ROBOT_NAV_API_ID_START_ALL); }
int32_t NavClient::SendCode1824() { return SendSimpleCode(ROBOT_NAV_API_ID_STOP_ALL); }

int32_t NavClient::SendCode1810(double goal_index, double x, double y, double z,
                                double roll, double pitch, double yaw, double w,
                                double stay_time,
                                const std::string& goal_meta) {
    control_messages::Command& cmd = NavCommandBuffer();
    cmd.cmd = ROBOT_NAV_API_ID_SEND_GOAL;
    cmd.params[0] = goal_index;
    cmd.params[1] = x;
    cmd.params[2] = y;
    cmd.params[3] = z;
    cmd.params[4] = roll;
    cmd.params[5] = pitch;
    cmd.params[6] = yaw;
    cmd.params[7] = w;
    cmd.params[8] = stay_time;
    cmd.goal_meta = goal_meta;
    if (!NavLcmInstance().good()) {
        std::cerr << "[NavClient] LCM init failed, lcm_url=" << NavLcmUrl() << std::endl;
        return -1;
    }
    std::cout << "[NavClient] publish cmd=" << ROBOT_NAV_API_ID_SEND_GOAL
              << " channel=UPPER_dogNAV_1"
              << " lcm_url=" << NavLcmUrl()
              << " goal_index=" << goal_index << std::endl;
    NavPublisherInstance().writeNav(&cmd);
    return 0;
}

void NavClient::setResponseCallback(std::function<void(int32_t code)> callback) {
    m_response_callback = callback;
}

int32_t NavClient::getLastResponseCode() const {
    return m_last_response_code;
}

bool NavClient::hasReceivedResponse(int32_t code) const {
    return m_received_response_codes.find(code) != m_received_response_codes.end();
}

void NavClient::updateResponseCode(int32_t code) {
    m_last_response_code = code;
    m_received_response_codes.insert(code);
    if (m_response_callback) {
        m_response_callback(code);
    }
}

}
}
