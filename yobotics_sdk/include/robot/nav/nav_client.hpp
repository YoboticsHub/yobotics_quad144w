#ifndef __MIT_ROBOT_E15_NAV_CLIENT_HPP__
#define __MIT_ROBOT_E15_NAV_CLIENT_HPP__

#include <decl.hpp>
#include <functional>

namespace yobotics
{
namespace robot
{
class NavClient
{
public:
    explicit NavClient();

    int32_t SendCode1801();
    int32_t SendCode1802();
    int32_t SendCode1803();
    int32_t SendCode1804();
    int32_t SendCode1805();
    int32_t SendCode1806();
    int32_t SendCode1807();
    int32_t SendCode1808();
    int32_t SendCode1800();
    int32_t SendCode1809();
    int32_t SendCode1810(double goal_index, double x, double y, double z,
                         double roll, double pitch, double yaw, double w,
                         double stay_time = 0.0,
                         const std::string& goal_meta = std::string());
    int32_t SendCode1820();
    int32_t SendCode1823();
    int32_t SendCode1824();

    void setResponseCallback(std::function<void(int32_t code)> callback);
    int32_t getLastResponseCode() const;
    bool hasReceivedResponse(int32_t code) const;
    void updateResponseCode(int32_t code);

private:
    int32_t SendSimpleCode(int32_t code);
    void ResetParams();

private:
    std::function<void(int32_t)> m_response_callback;
    int32_t m_last_response_code;
    std::set<int32_t> m_received_response_codes;
};

}
}

#endif
