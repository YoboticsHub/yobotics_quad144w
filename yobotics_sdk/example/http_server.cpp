#include "sport/sport_client.hpp"
#include "nav/nav_client.hpp"
#include "nav/nav_api.hpp"
#include "channel_subscriber.hpp"
#include "httplib.hpp"
#include "json.hpp"
#include "common/lcm_types/cpp/nav_enable_t.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>

using json = nlohmann::json;
using namespace httplib;
using namespace yobotics::robot;

namespace {

const std::string kDefaultHost = "192.168.1.100";
const int kDefaultPort = 8080;
const std::string kDefaultToken = "Y20W_Robot_Secure_Token_123";
const std::string kTokenPrefix = "Bearer ";
const char* kDefaultLcmUrl = "udpm://239.255.76.67:7667?ttl=255";

enum E15Mode {
    E15_MODE_PASSIVE = 0,
    E15_MODE_DAMP,
    E15_MODE_RECOVERY_STAND,
    E15_MODE_STAND_DOWN,
    E15_MODE_RL_WALK,
    E15_MODE_DEVELOPMENT
};

struct RobotStateCache {
    sport_client_state_t quad_state{};
    quad_joint_state_t leg_state{};
    quad_joint_command_t leg_cmd{};
    bool has_data = false;
};

struct NavStateCache {
    int32_t code = 0;
    double data[8] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    double other_data[7] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    double extra_data[3] = {0.0, 0.0, 0.0};
    bool has_data = false;
};

struct NavCommandTracker {
    int32_t request_code = 0;
    int32_t expected_response_code = 0;
    std::string cmd_type;
    bool has_pending_command = false;
    bool ack_received = false;
    bool goal_reached = false;
};

struct MotionCommand {
    E15Mode mode = E15_MODE_DAMP;
    bool nav_enabled = false;
    float vx = 0.0f;
    float vy = 0.0f;
    float vyaw = 0.0f;
    float body_height = 0.0f;
    float roll = 0.0f;
    float pitch = 0.0f;
};

std::mutex g_state_mutex;
std::mutex g_nav_state_mutex;
std::mutex g_nav_command_mutex;
std::mutex g_command_mutex;
std::mutex g_sport_mutex;
std::mutex g_nav_enable_mutex;

RobotStateCache g_state_cache;
NavStateCache g_nav_state_cache;
NavCommandTracker g_nav_command_tracker;
MotionCommand g_motion_command;
SportClient g_sport_client;
NavClient g_nav_client;
std::unique_ptr<lcm::LCM> g_nav_enable_lcm;

std::atomic<bool> g_running(false);
std::thread g_state_thread;
std::thread g_control_thread;
Server* g_server = nullptr;

std::string get_env_string(const char* key, const std::string& fallback) {
    const char* value = std::getenv(key);
    return (value && value[0] != '\0') ? std::string(value) : fallback;
}

int get_env_int(const char* key, int fallback) {
    const char* value = std::getenv(key);
    if (!value || value[0] == '\0') {
        return fallback;
    }
    try {
        return std::stoi(value);
    } catch (...) {
        return fallback;
    }
}

std::string resolve_lcm_url() {
    return get_env_string("YOBOTICS_LCM_URL", kDefaultLcmUrl);
}

template <typename T>
T clamp_value(T value, T min_value, T max_value) {
    if (value < min_value) return min_value;
    if (value > max_value) return max_value;
    return value;
}

const char* mode_to_string(E15Mode mode) {
    switch (mode) {
    case E15_MODE_PASSIVE: return "passive";
    case E15_MODE_DAMP: return "damp";
    case E15_MODE_RECOVERY_STAND: return "recovery_stand";
    case E15_MODE_STAND_DOWN: return "stand_down";
    case E15_MODE_RL_WALK: return "rl_walk";
    case E15_MODE_DEVELOPMENT: return "development";
    default: return "unknown";
    }
}

bool parse_mode_string(const std::string& mode_str, E15Mode& out_mode) {
    if (mode_str == "passive") out_mode = E15_MODE_PASSIVE;
    else if (mode_str == "damp") out_mode = E15_MODE_DAMP;
    else if (mode_str == "recovery_stand") out_mode = E15_MODE_RECOVERY_STAND;
    else if (mode_str == "stand_down") out_mode = E15_MODE_STAND_DOWN;
    else if (mode_str == "rl_walk") out_mode = E15_MODE_RL_WALK;
    else if (mode_str == "development") out_mode = E15_MODE_DEVELOPMENT;
    else return false;
    return true;
}

bool is_motion_mode(E15Mode mode) {
    return mode == E15_MODE_RL_WALK || mode == E15_MODE_DEVELOPMENT;
}

void normalize_motion_command(MotionCommand& command) {
    command.vx = clamp_value(command.vx, -1.5f, 1.5f);
    command.vy = clamp_value(command.vy, -1.0f, 1.0f);
    command.vyaw = clamp_value(command.vyaw, -1.5f, 1.5f);
    command.body_height = clamp_value(command.body_height, -0.20f, 0.20f);
    command.roll = clamp_value(command.roll, -0.50f, 0.50f);
    command.pitch = clamp_value(command.pitch, -0.50f, 0.50f);

    if (!is_motion_mode(command.mode)) {
        command.vx = 0.0f;
        command.vy = 0.0f;
        command.vyaw = 0.0f;
        command.body_height = 0.0f;
        command.roll = 0.0f;
        command.pitch = 0.0f;
    }
}

json to_json_array(const float* values, int size) {
    json arr = json::array();
    for (int i = 0; i < size; ++i) {
        arr.push_back(values[i]);
    }
    return arr;
}

json to_json_array(const double* values, int size) {
    json arr = json::array();
    for (int i = 0; i < size; ++i) {
        arr.push_back(values[i]);
    }
    return arr;
}

// Integer arrays are used for discrete status/fault fields in the LCM
// messages (for example, quad_joint_state_t::joint_fault).  Keep these
// values as JSON integers instead of requiring an unsafe conversion to a
// floating-point array.
json to_json_array(const int32_t* values, int size) {
    json arr = json::array();
    for (int i = 0; i < size; ++i) {
        arr.push_back(values[i]);
    }
    return arr;
}

json build_command_json(const MotionCommand& command) {
    return json{
        {"mode", mode_to_string(command.mode)},
        {"nav_enabled", command.nav_enabled},
        {"vx", command.vx},
        {"vy", command.vy},
        {"vyaw", command.vyaw},
        {"body_height", command.body_height},
        {"roll", command.roll},
        {"pitch", command.pitch}
    };
}

void publish_nav_enable(bool enabled) {
    std::lock_guard<std::mutex> lock(g_nav_enable_mutex);
    if (!g_nav_enable_lcm || !g_nav_enable_lcm->good()) {
        throw std::runtime_error("nav enable lcm not initialized");
    }
    nav_enable_t msg;
    msg.enable = enabled ? 1 : 0;
    g_nav_enable_lcm->publish("NAV_ENABLE_CTRL", &msg);
}

const char* nav_code_to_string(int32_t code) {
    switch (code) {
    case ROBOT_NAV_RESPONSE_CODE_2025: return "nav general response";
    case ROBOT_NAV_RESPONSE_CODE_20251: return "nav send goal ack";
    case ROBOT_NAV_RESPONSE_CODE_20260: return "end goal program ack";
    case ROBOT_NAV_RESPONSE_CODE_20261: return "start mapping ack";
    case ROBOT_NAV_RESPONSE_CODE_20262: return "end mapping ack";
    case ROBOT_NAV_RESPONSE_CODE_20263: return "start cutter ack";
    case ROBOT_NAV_RESPONSE_CODE_20264: return "end cutter ack";
    case ROBOT_NAV_RESPONSE_CODE_20265: return "start localization ack";
    case ROBOT_NAV_RESPONSE_CODE_20266: return "end localization ack";
    case ROBOT_NAV_RESPONSE_CODE_20267: return "start nav ack";
    case ROBOT_NAV_RESPONSE_CODE_20268: return "end nav ack";
    case ROBOT_NAV_RESPONSE_CODE_20269: return "start goal program ack";
    case ROBOT_NAV_RESPONSE_CODE_1821: return "clear goal ack";
    case ROBOT_NAV_RESPONSE_CODE_1822: return "goal cleared/related response";
    case ROBOT_NAV_RESPONSE_CODE_20270: return "goal reached";
    case 3001: return "position update";
    case 3002: return "velocity update";
    default: return "unknown";
    }
}

int32_t expected_nav_response_code(const std::string& cmd_type) {
    if (cmd_type == "start_mapping" || cmd_type == "send_code_1801") return ROBOT_NAV_RESPONSE_CODE_20261;
    if (cmd_type == "end_mapping" || cmd_type == "send_code_1802") return ROBOT_NAV_RESPONSE_CODE_20262;
    if (cmd_type == "start_cutter" || cmd_type == "START_CUTTER" || cmd_type == "send_code_1803") return ROBOT_NAV_RESPONSE_CODE_20263;
    if (cmd_type == "end_cutter" || cmd_type == "END_CUTTER" || cmd_type == "send_code_1804") return ROBOT_NAV_RESPONSE_CODE_20264;
    if (cmd_type == "start_localization" || cmd_type == "START_LOCALIZATION" || cmd_type == "send_code_1805") return ROBOT_NAV_RESPONSE_CODE_20265;
    if (cmd_type == "end_localization" || cmd_type == "END_LOCALIZATION" || cmd_type == "send_code_1806") return ROBOT_NAV_RESPONSE_CODE_20266;
    if (cmd_type == "start_nav" || cmd_type == "START_NAV" || cmd_type == "send_code_1807") return ROBOT_NAV_RESPONSE_CODE_20267;
    if (cmd_type == "end_nav" || cmd_type == "END_NAV" || cmd_type == "send_code_1808") return ROBOT_NAV_RESPONSE_CODE_20268;
    if (cmd_type == "end_goal_program" || cmd_type == "END_GOAL_PROGRAM" || cmd_type == "send_code_1800") return ROBOT_NAV_RESPONSE_CODE_20260;
    if (cmd_type == "start_goal_program" || cmd_type == "START_GOAL_PROGRAM" || cmd_type == "send_code_1809") return ROBOT_NAV_RESPONSE_CODE_20269;
    if (cmd_type == "send_goal" || cmd_type == "SEND_GOAL" || cmd_type == "send_code_1810") return ROBOT_NAV_RESPONSE_CODE_2026;
    if (cmd_type == "clear_goal" || cmd_type == "CLEAR_GOAL" || cmd_type == "send_code_1820") return ROBOT_NAV_RESPONSE_CODE_1821;
    if (cmd_type == "start_all" || cmd_type == "send_code_1823") return ROBOT_NAV_RESPONSE_CODE_20271;
    if (cmd_type == "stop_all" || cmd_type == "send_code_1824") return ROBOT_NAV_RESPONSE_CODE_20272;
    return 0;
}

int32_t nav_request_code(const std::string& cmd_type) {
    if (cmd_type == "start_mapping" || cmd_type == "send_code_1801") return ROBOT_NAV_API_ID_START_MAPPING;
    if (cmd_type == "end_mapping" || cmd_type == "send_code_1802") return ROBOT_NAV_API_ID_END_MAPPING;
    if (cmd_type == "start_cutter" || cmd_type == "START_CUTTER" || cmd_type == "send_code_1803") return ROBOT_NAV_API_ID_START_CUTTER;
    if (cmd_type == "end_cutter" || cmd_type == "END_CUTTER" || cmd_type == "send_code_1804") return ROBOT_NAV_API_ID_END_CUTTER;
    if (cmd_type == "start_localization" || cmd_type == "START_LOCALIZATION" || cmd_type == "send_code_1805") return ROBOT_NAV_API_ID_START_LOCALIZATION;
    if (cmd_type == "end_localization" || cmd_type == "END_LOCALIZATION" || cmd_type == "send_code_1806") return ROBOT_NAV_API_ID_END_LOCALIZATION;
    if (cmd_type == "start_nav" || cmd_type == "START_NAV" || cmd_type == "send_code_1807") return ROBOT_NAV_API_ID_START_NAV;
    if (cmd_type == "end_nav" || cmd_type == "END_NAV" || cmd_type == "send_code_1808") return ROBOT_NAV_API_ID_END_NAV;
    if (cmd_type == "end_goal_program" || cmd_type == "END_GOAL_PROGRAM" || cmd_type == "send_code_1800") return ROBOT_NAV_API_ID_END_GOAL_PROGRAM;
    if (cmd_type == "start_goal_program" || cmd_type == "START_GOAL_PROGRAM" || cmd_type == "send_code_1809") return ROBOT_NAV_API_ID_START_GOAL_PROGRAM;
    if (cmd_type == "send_goal" || cmd_type == "SEND_GOAL" || cmd_type == "send_code_1810") return ROBOT_NAV_API_ID_SEND_GOAL;
    if (cmd_type == "clear_goal" || cmd_type == "CLEAR_GOAL" || cmd_type == "send_code_1820") return ROBOT_NAV_API_ID_CLEAR_GOAL;
    if (cmd_type == "start_all" || cmd_type == "send_code_1823") return ROBOT_NAV_API_ID_START_ALL;
    if (cmd_type == "stop_all" || cmd_type == "send_code_1824") return ROBOT_NAV_API_ID_STOP_ALL;
    return 0;
}

void record_nav_command(const std::string& cmd_type) {
    NavCommandTracker tracker;
    tracker.request_code = nav_request_code(cmd_type);
    tracker.expected_response_code = expected_nav_response_code(cmd_type);
    tracker.cmd_type = cmd_type;
    tracker.has_pending_command = (tracker.request_code != 0);
    tracker.ack_received = false;
    tracker.goal_reached = false;

    std::lock_guard<std::mutex> lock(g_nav_command_mutex);
    g_nav_command_tracker = tracker;
}

void update_nav_command_state(int32_t response_code) {
    std::lock_guard<std::mutex> lock(g_nav_command_mutex);
    if (!g_nav_command_tracker.has_pending_command && response_code != ROBOT_NAV_RESPONSE_CODE_20270) {
        return;
    }

    if (response_code == g_nav_command_tracker.expected_response_code && response_code != 0) {
        g_nav_command_tracker.ack_received = true;
        g_nav_command_tracker.has_pending_command = false;
    }

    if (response_code == ROBOT_NAV_RESPONSE_CODE_20270) {
        g_nav_command_tracker.goal_reached = true;
        if (g_nav_command_tracker.request_code == ROBOT_NAV_API_ID_SEND_GOAL) {
            g_nav_command_tracker.has_pending_command = false;
        }
    }
}

const char* nav_summary_status(const NavCommandTracker& tracker, int32_t nav_code) {
    if (tracker.goal_reached || nav_code == ROBOT_NAV_RESPONSE_CODE_20270) {
        return "goal_reached";
    }
    if (tracker.has_pending_command) {
        return "waiting_ack";
    }
    if (tracker.ack_received) {
        return "ack_received";
    }
    return "idle";
}

json build_nav_status_json(const NavStateCache& nav_state) {
    json status = {
        {"has_data", nav_state.has_data},
        {"code", nav_state.code},
        {"code_desc", nav_code_to_string(nav_state.code)},
        {"data", to_json_array(nav_state.data, 8)},
        {"other_data", to_json_array(nav_state.other_data, 7)},
        {"extra_data", to_json_array(nav_state.extra_data, 3)}
    };

    status["position"] = {
        {"x", nav_state.other_data[0]},
        {"y", nav_state.other_data[1]},
        {"z", nav_state.other_data[2]}
    };
    status["attitude"] = {
        {"roll", nav_state.other_data[3]},
        {"pitch", nav_state.other_data[4]},
        {"yaw", nav_state.other_data[5]},
        {"w", nav_state.other_data[6]}
    };
    status["velocity"] = {
        {"vx", nav_state.extra_data[0]},
        {"vy", nav_state.extra_data[1]},
        {"vyaw", nav_state.extra_data[2]}
    };

    if (nav_state.code == ROBOT_NAV_RESPONSE_CODE_20270) {
        status["goal_reached"] = true;
        status["goal_index"] = nav_state.data[0];
    } else {
        status["goal_reached"] = false;
    }

    return status;
}

double goal_index_from_name(const json& body) {
    if (!body.contains("name")) {
        return 0.0;
    }

    if (body["name"].is_number()) {
        return body["name"].get<double>();
    }

    if (body["name"].is_string()) {
        const std::string name = body["name"].get<std::string>();
        try {
            size_t parsed_chars = 0;
            const double value = std::stod(name, &parsed_chars);
            if (parsed_chars == name.size()) {
                return value;
            }
        } catch (...) {
        }
    }

    return 0.0;
}

json build_goal_meta_from_body(const json& body) {
    json meta = json::object();

    if (!body.contains("name") || (!body["name"].is_string() && !body["name"].is_number())) {
        throw std::runtime_error("field 'name' must be a string or number");
    }
    meta["name"] = body["name"];

    if (!body.contains("play") || !body["play"].is_boolean()) {
        throw std::runtime_error("field 'play' must be a boolean");
    }
    meta["play"] = body["play"];

    if (!body.contains("speech_text") || !body["speech_text"].is_string()) {
        throw std::runtime_error("field 'speech_text' must be a string");
    }
    meta["speech_text"] = body["speech_text"];

    if (!body.contains("actions") || !body["actions"].is_array()) {
        throw std::runtime_error("field 'actions' must be an array");
    }
    for (const auto& action : body["actions"]) {
        if (!action.is_object()) {
            throw std::runtime_error("field 'actions' must contain objects");
        }
        if (action.contains("flag") && !action["flag"].is_number()) {
            throw std::runtime_error("field 'actions[].flag' must be a number");
        }
        if (action.contains("duration") && !action["duration"].is_number()) {
            throw std::runtime_error("field 'actions[].duration' must be a number");
        }
    }
    meta["actions"] = body["actions"];

    return meta;
}

int32_t dispatch_nav_command(const std::string& cmd_type, const json& body) {
    if (cmd_type == "start_mapping" || cmd_type == "send_code_1801") return g_nav_client.SendCode1801();
    if (cmd_type == "end_mapping" || cmd_type == "send_code_1802") return g_nav_client.SendCode1802();
    if (cmd_type == "start_cutter" || cmd_type == "START_CUTTER" || cmd_type == "send_code_1803") return g_nav_client.SendCode1803();
    if (cmd_type == "end_cutter" || cmd_type == "END_CUTTER" || cmd_type == "send_code_1804") return g_nav_client.SendCode1804();
    if (cmd_type == "start_localization" || cmd_type == "START_LOCALIZATION" || cmd_type == "send_code_1805") return g_nav_client.SendCode1805();
    if (cmd_type == "end_localization" || cmd_type == "END_LOCALIZATION" || cmd_type == "send_code_1806") return g_nav_client.SendCode1806();
    if (cmd_type == "start_nav" || cmd_type == "START_NAV" || cmd_type == "send_code_1807") return g_nav_client.SendCode1807();
    if (cmd_type == "end_nav" || cmd_type == "END_NAV" || cmd_type == "send_code_1808") return g_nav_client.SendCode1808();
    if (cmd_type == "end_goal_program" || cmd_type == "END_GOAL_PROGRAM" || cmd_type == "send_code_1800") return g_nav_client.SendCode1800();
    if (cmd_type == "start_goal_program" || cmd_type == "START_GOAL_PROGRAM" || cmd_type == "send_code_1809") return g_nav_client.SendCode1809();
    if (cmd_type == "clear_goal" || cmd_type == "CLEAR_GOAL" || cmd_type == "send_code_1820") return g_nav_client.SendCode1820();
    if (cmd_type == "start_all" || cmd_type == "send_code_1823") return g_nav_client.SendCode1823();
    if (cmd_type == "stop_all" || cmd_type == "send_code_1824") return g_nav_client.SendCode1824();

    if (cmd_type == "send_goal" || cmd_type == "SEND_GOAL" || cmd_type == "send_code_1810") {
        if (!body.contains("pos") || !body["pos"].is_array() || body["pos"].size() != 7) {
            throw std::runtime_error("field 'pos' must be an array with 7 numbers");
        }

        double pos[7] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0};
        for (int i = 0; i < 7; ++i) {
            if (!body["pos"][i].is_number()) {
                throw std::runtime_error("field 'pos' must contain only numbers");
            }
            pos[i] = body["pos"][i].get<double>();
        }
        if (!body.contains("stay_time") || !body["stay_time"].is_number()) {
            throw std::runtime_error("field 'stay_time' must be a number");
        }
        const double stay_time = body["stay_time"].get<double>();

        const double goal_index = goal_index_from_name(body);
        const std::string goal_meta = build_goal_meta_from_body(body).dump();
        return g_nav_client.SendCode1810(goal_index, pos[0], pos[1], pos[2],
                                         pos[3], pos[4], pos[5], pos[6],
                                         stay_time, goal_meta);
    }

    throw std::runtime_error("unsupported nav cmd_type");
}

json build_nav_success_response(const std::string& cmd_type, const json& body) {
    json data = {
        {"cmd_type", cmd_type},
        {"request_code", nav_request_code(cmd_type)},
        {"expected_response_code", expected_nav_response_code(cmd_type)}
    };

    if ((cmd_type == "send_goal" || cmd_type == "SEND_GOAL" || cmd_type == "send_code_1810") && body.contains("pos")) {
        data["name"] = body["name"];
        data["pos"] = body["pos"];
        data["stay_time"] = body["stay_time"];
        data["play"] = body["play"];
        data["speech_text"] = body["speech_text"];
        data["actions"] = body["actions"];
    }

    return json{
        {"code", 0},
        {"msg", "nav command sent"},
        {"data", data}
    };
}

void apply_cors_headers(Response& res) {
    res.set_header("Access-Control-Allow-Origin", "*");
    res.set_header("Access-Control-Allow-Headers", "Authorization, Content-Type");
    res.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
}

void set_json_response(Response& res, int status, const json& body) {
    res.status = status;
    res.set_content(body.dump(), "application/json");
    apply_cors_headers(res);
}

bool validate_request_token(const Request& req) {
    const std::string auth = req.get_header_value("Authorization");
    if (auth.compare(0, kTokenPrefix.size(), kTokenPrefix) != 0) {
        return false;
    }
    const std::string expected = get_env_string("ROBOT_HTTP_TOKEN", kDefaultToken);
    return auth.substr(kTokenPrefix.size()) == expected;
}

void stop_server() {
    g_running.store(false);
    if (g_server) {
        g_server->stop();
    }
}

void signal_handler(int) {
    stop_server();
}

void state_subscribe_loop() {
    lcm::LCM lcm(resolve_lcm_url());
    if (!lcm.good()) {
        std::cerr << "[ERROR] Failed to initialize LCM for state subscriber" << std::endl;
        return;
    }

    ChannelSubscriber subscriber(&lcm);
    while (g_running.load()) {
        RobotStateCache next_state;
        control_messages::Response nav_response{};
        subscriber.read(&next_state.quad_state);
        subscriber.read(&next_state.leg_state);
        subscriber.read(&next_state.leg_cmd);
        subscriber.readNavData(&nav_response);
        next_state.has_data = true;

        {
            std::lock_guard<std::mutex> lock(g_state_mutex);
            g_state_cache = next_state;
        }

        {
            std::lock_guard<std::mutex> lock(g_nav_state_mutex);

            if (nav_response.code == 3001) {
                g_nav_state_cache.has_data = true;
                for (int i = 0; i < 7; ++i) {
                    g_nav_state_cache.other_data[i] = nav_response.other_data[i].value;
                }
            } else if (nav_response.code == 3002) {
                g_nav_state_cache.has_data = true;
                for (int i = 0; i < 3; ++i) {
                    g_nav_state_cache.extra_data[i] = nav_response.extra_data[i].value;
                }
            } else {
                g_nav_state_cache.code = nav_response.code;
                g_nav_state_cache.has_data = (nav_response.code != 0);
                for (int i = 0; i < 8; ++i) {
                    g_nav_state_cache.data[i] = nav_response.data[i].value;
                }
                for (int i = 0; i < 7; ++i) {
                    g_nav_state_cache.other_data[i] = nav_response.other_data[i].value;
                }
                for (int i = 0; i < 3; ++i) {
                    g_nav_state_cache.extra_data[i] = nav_response.extra_data[i].value;
                }
            }
        }

        if (nav_response.code != 0 && nav_response.code != 3001 && nav_response.code != 3002) {
            g_nav_client.updateResponseCode(nav_response.code);
            update_nav_command_state(nav_response.code);
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
}

void control_loop() {
    while (g_running.load()) {
        MotionCommand command;
        {
            std::lock_guard<std::mutex> lock(g_command_mutex);
            command = g_motion_command;
        }

        {
            std::lock_guard<std::mutex> lock(g_sport_mutex);
            g_sport_client.EnableLCMControl();
            switch (command.mode) {
            case E15_MODE_PASSIVE: g_sport_client.Passive(); break;
            case E15_MODE_DAMP: g_sport_client.Damp(); break;
            case E15_MODE_RECOVERY_STAND: g_sport_client.RecoveryStand(); break;
            case E15_MODE_STAND_DOWN: g_sport_client.StandDown(); break;
            case E15_MODE_RL_WALK: g_sport_client.RLWalk(); break;
            case E15_MODE_DEVELOPMENT: g_sport_client.Development(); break;
            }

            if (is_motion_mode(command.mode)) {
                g_sport_client.Move(command.vx, command.vy, command.vyaw);
                g_sport_client.BodyHeight(command.body_height);
                g_sport_client.Euler(command.roll, command.pitch);
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    std::lock_guard<std::mutex> lock(g_sport_mutex);
    g_sport_client.Move(0.0f, 0.0f, 0.0f);
    g_sport_client.BodyHeight(0.0f);
    g_sport_client.Euler(0.0f, 0.0f);
    g_sport_client.Damp();
}

void handle_motion_request(const Request& req, Response& res) {
    try {
        const json body = json::parse(req.body);
        MotionCommand next_command;

        {
            std::lock_guard<std::mutex> lock(g_command_mutex);
            next_command = g_motion_command;
        }

        if (body.contains("mode")) {
            if (!body["mode"].is_string()) {
                set_json_response(res, 400, {
                    {"code", 400},
                    {"msg", "field 'mode' must be a string"}
                });
                return;
            }

            E15Mode parsed_mode;
            if (!parse_mode_string(body["mode"].get<std::string>(), parsed_mode)) {
                set_json_response(res, 400, {
                    {"code", 400},
                    {"msg", "invalid mode"}
                });
                return;
            }
            next_command.mode = parsed_mode;
        }

        if (body.contains("nav_enabled")) {
            if (!body["nav_enabled"].is_boolean()) {
                set_json_response(res, 400, {
                    {"code", 400},
                    {"msg", "field 'nav_enabled' must be a boolean"}
                });
                return;
            }
            next_command.nav_enabled = body["nav_enabled"].get<bool>();
        }

        if (body.contains("vx")) next_command.vx = body["vx"].get<float>();
        if (body.contains("vy")) next_command.vy = body["vy"].get<float>();
        if (body.contains("vyaw")) next_command.vyaw = body["vyaw"].get<float>();
        if (body.contains("body_height")) next_command.body_height = body["body_height"].get<float>();
        if (body.contains("roll")) next_command.roll = body["roll"].get<float>();
        if (body.contains("pitch")) next_command.pitch = body["pitch"].get<float>();

        normalize_motion_command(next_command);

        {
            std::lock_guard<std::mutex> lock(g_command_mutex);
            g_motion_command = next_command;
        }

        set_json_response(res, 200, {
            {"code", 0},
            {"msg", "motion command updated"},
            {"data", build_command_json(next_command)}
        });
    } catch (const std::exception& e) {
        set_json_response(res, 400, {
            {"code", 400},
            {"msg", std::string("invalid json: ") + e.what()}
        });
    }
}

void handle_nav_enable_request(const Request& req, Response& res) {
    try {
        const json body = json::parse(req.body);
        if (!body.contains("nav_enabled") || !body["nav_enabled"].is_boolean()) {
            set_json_response(res, 400, {
                {"code", 400},
                {"msg", "field 'nav_enabled' must be a boolean"}
            });
            return;
        }

        MotionCommand next_command;
        {
            std::lock_guard<std::mutex> lock(g_command_mutex);
            next_command = g_motion_command;
        }

        next_command.nav_enabled = body["nav_enabled"].get<bool>();
        if (next_command.nav_enabled && next_command.mode != E15_MODE_RL_WALK) {
            set_json_response(res, 400, {
                {"code", 400},
                {"msg", "nav enable requires rl_walk mode"}
            });
            return;
        }

        normalize_motion_command(next_command);
        publish_nav_enable(next_command.nav_enabled);

        {
            std::lock_guard<std::mutex> lock(g_command_mutex);
            g_motion_command = next_command;
        }

        set_json_response(res, 200, {
            {"code", 0},
            {"msg", "nav enable updated"},
            {"data", build_command_json(next_command)}
        });
    } catch (const std::exception& e) {
        set_json_response(res, 400, {
            {"code", 400},
            {"msg", std::string("invalid json: ") + e.what()}
        });
    }
}

void handle_nav_request(const Request& req, Response& res) {
    try {
        const json body = json::parse(req.body);

        if (!body.contains("cmd_type") || !body["cmd_type"].is_string()) {
            set_json_response(res, 400, {
                {"code", 400},
                {"msg", "field 'cmd_type' must be a string"}
            });
            return;
        }

        const std::string cmd_type = body["cmd_type"].get<std::string>();
        std::cout << "[HTTP] /control/nav cmd_type=" << cmd_type << std::endl;
        const int32_t sdk_ret = dispatch_nav_command(cmd_type, body);
        if (sdk_ret != 0) {
            set_json_response(res, 500, {
                {"code", sdk_ret},
                {"msg", "failed to send nav command"}
            });
            return;
        }

        record_nav_command(cmd_type);
        set_json_response(res, 200, build_nav_success_response(cmd_type, body));
    } catch (const std::exception& e) {
        set_json_response(res, 400, {
            {"code", 400},
            {"msg", e.what()}
        });
    }
}

void handle_nav_status_request(const Request&, Response& res) {
    NavStateCache nav_state;
    NavCommandTracker tracker;
    {
        std::lock_guard<std::mutex> lock(g_nav_state_mutex);
        nav_state = g_nav_state_cache;
    }
    {
        std::lock_guard<std::mutex> lock(g_nav_command_mutex);
        tracker = g_nav_command_tracker;
    }

    const bool matches_expected = tracker.expected_response_code != 0 && nav_state.code == tracker.expected_response_code;
    const bool is_goal_reached = nav_state.code == ROBOT_NAV_RESPONSE_CODE_20270 || tracker.goal_reached;
    const char* summary_status = nav_summary_status(tracker, nav_state.code);

    set_json_response(res, 200, {
        {"code", 0},
        {"msg", "ok"},
        {"data", {
            {"nav_state", build_nav_status_json(nav_state)},
            {"last_command", {
                {"has_pending_command", tracker.has_pending_command},
                {"cmd_type", tracker.cmd_type},
                {"request_code", tracker.request_code},
                {"expected_response_code", tracker.expected_response_code},
                {"expected_response_desc", nav_code_to_string(tracker.expected_response_code)},
                {"matched_expected_response", matches_expected},
                {"ack_received", tracker.ack_received},
                {"goal_reached", tracker.goal_reached}
            }},
            {"nav_client", {
                {"last_response_code", g_nav_client.getLastResponseCode()},
                {"last_response_desc", nav_code_to_string(g_nav_client.getLastResponseCode())},
                {"has_goal_reached_response", g_nav_client.hasReceivedResponse(ROBOT_NAV_RESPONSE_CODE_20270)}
            }},
            {"summary", {
                {"status", summary_status},
                {"goal_reached", is_goal_reached},
                {"code_desc", nav_code_to_string(nav_state.code)}
            }}
        }}
    });
}

void handle_stop_request(const Request&, Response& res) {
    MotionCommand next_command;
    normalize_motion_command(next_command);

    {
        std::lock_guard<std::mutex> lock(g_command_mutex);
        g_motion_command = next_command;
    }

    set_json_response(res, 200, {
        {"code", 0},
        {"msg", "robot stopped"},
        {"data", build_command_json(next_command)}
    });
}

void handle_status_request(const Request&, Response& res) {
    RobotStateCache state;
    MotionCommand command;
    NavStateCache nav_state;

    {
        std::lock_guard<std::mutex> lock(g_state_mutex);
        state = g_state_cache;
    }
    {
        std::lock_guard<std::mutex> lock(g_command_mutex);
        command = g_motion_command;
    }
    {
        std::lock_guard<std::mutex> lock(g_nav_state_mutex);
        nav_state = g_nav_state_cache;
    }

    set_json_response(res, 200, {
        {"code", 0},
        {"msg", "ok"},
        {"data", {
            {"has_state", state.has_data},
            {"command", build_command_json(command)},
            {"nav_state", build_nav_status_json(nav_state)},
            {"quad_state", {
                {"rpy", to_json_array(state.quad_state.rpy, 3)},
                {"power", to_json_array(state.quad_state.power, 2)},
                {"v", state.quad_state.v},
                {"h", state.quad_state.h},
                {"state", state.quad_state.state},
                {"fault", state.quad_state.fault}
            }},
            {"leg_state", {
                {"joint_q", to_json_array(state.leg_state.joint_q, 12)},
                {"joint_qd", to_json_array(state.leg_state.joint_qd, 12)},
                {"joint_tau", to_json_array(state.leg_state.joint_tau, 12)},
                {"joint_fault", to_json_array(state.leg_state.joint_fault, 12)},
                {"joint_temp", to_json_array(state.leg_state.joint_temp, 12)}
            }},
            {"leg_command", {
                {"joint_des_q", to_json_array(state.leg_cmd.joint_des_q, 12)},
                {"joint_des_qd", to_json_array(state.leg_cmd.joint_des_qd, 12)},
                {"joint_des_tau", to_json_array(state.leg_cmd.joint_des_tau, 12)},
                {"joint_des_kp", to_json_array(state.leg_cmd.joint_des_kp, 12)},
                {"joint_des_kd", to_json_array(state.leg_cmd.joint_des_kd, 12)}
            }}
        }}
    });
}

}  // namespace

int main() {
    const std::string http_host = get_env_string("SERVER_HOST", kDefaultHost);
    const int http_port = get_env_int("SERVER_PORT", kDefaultPort);

    g_nav_enable_lcm.reset(new lcm::LCM(resolve_lcm_url()));

    std::signal(SIGINT, signal_handler);
#ifdef SIGTERM
    std::signal(SIGTERM, signal_handler);
#endif

    g_running.store(true);
    g_state_thread = std::thread(state_subscribe_loop);
    g_control_thread = std::thread(control_loop);

    Server svr;
    g_server = &svr;

    svr.set_pre_routing_handler([](const Request& req, Response& res) {
        apply_cors_headers(res);

        if (req.method == "OPTIONS") {
            res.status = 200;
            return Server::HandlerResponse::Handled;
        }

        if ((req.method == "GET" || req.method == "POST") &&
            !validate_request_token(req)) {
            set_json_response(res, 401, {
                {"code", 401},
                {"msg", "Unauthorized: invalid or missing token"}
            });
            return Server::HandlerResponse::Handled;
        }

        return Server::HandlerResponse::Unhandled;
    });

    svr.Get("/control/status", handle_status_request);
    svr.Get("/control/nav/status", handle_nav_status_request);
    svr.Post("/control/motion", handle_motion_request);
    svr.Post("/control/nav/enable", handle_nav_enable_request);
    svr.Post("/control/nav", handle_nav_request);
    svr.Post("/control/stop", handle_stop_request);

    std::cout << "[INFO] E15 HTTP server starting at http://"
              << http_host << ":" << http_port << std::endl;
    std::cout << "[INFO] Authorization token env: ROBOT_HTTP_TOKEN" << std::endl;
    std::cout << "[INFO] LCM URL: " << resolve_lcm_url() << std::endl;

    if (!svr.listen(http_host.c_str(), http_port)) {
        std::cerr << "[ERROR] Failed to start HTTP server on "
                  << http_host << ":" << http_port << std::endl;
    }

    stop_server();

    if (g_state_thread.joinable()) {
        g_state_thread.join();
    }
    if (g_control_thread.joinable()) {
        g_control_thread.join();
    }

    g_server = nullptr;
    return 0;
}
