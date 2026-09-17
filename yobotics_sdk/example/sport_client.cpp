#include "sport/sport_client.hpp"
#include <atomic>
#include <cstdio>
#include <termios.h>
#include <thread>
#include <unistd.h>

#define LINEAR_VELOCITY_X 0.05
#define LINEAR_VELOCITY_Y 0.05
#define ANGULAR_VELOCITY_Z 0.05
#define RELEASE_THRESHOLD 10
#define KEYBOARD_PERIOD_US 10000
#define BODY_HEIGHT_STEP 0.01
#define EULER_STEP 0.03

enum test_mode {
  mode_recovery_stand = 1,
  mode_stand_down = 2,
  mode_damp = 3,
  mode_rl_walk = 4,
  mode_development = 5,
  mode_exit = 99
};

std::atomic<int> TEST_MODE(mode_damp);
std::atomic<bool> keyboard_running(true);
std::atomic<bool> is_moving(false);

class Custom {
public:
  Custom() = default;

  char getch() {
    char buf = 0;
    struct termios old = {0};
    if (tcgetattr(0, &old) < 0)
      perror("tcsetattr()");
    old.c_lflag &= ~ICANON;
    old.c_lflag &= ~ECHO;
    old.c_cc[VMIN] = 1;
    old.c_cc[VTIME] = 0;
    if (tcsetattr(0, TCSANOW, &old) < 0)
      perror("tcsetattr ICANON");
    if (read(0, &buf, 1) < 0)
      perror("read()");
    old.c_lflag |= ICANON;
    old.c_lflag |= ECHO;
    if (tcsetattr(0, TCSADRAIN, &old) < 0)
      perror("tcsetattr ~ICANON");
    return buf;
  }

  bool CanMoveMode() const {
    const int m = TEST_MODE.load();
    return m == mode_rl_walk || m == mode_development;
  }

  bool CanPoseMode() const {
    const int m = TEST_MODE.load();
    return m == mode_rl_walk || m == mode_development;
  }

  void SendMoveCommand(double vx, double vy, double wz) {
    cmd_vx_ += vx;
    cmd_vy_ += vy;
    cmd_wz_ += wz;
    is_moving = true;
  }

  void SendStopCommand() {
    cmd_vx_ = 0.0;
    cmd_vy_ = 0.0;
    cmd_wz_ = 0.0;
    is_moving = false;
  }

  void ApplyPose() {
    sport_client.BodyHeight(body_height_cmd);
    sport_client.Euler(roll_cmd, pitch_cmd);
    printf("姿态: body=%.2f roll=%.2f pitch=%.2f\n", body_height_cmd, roll_cmd, pitch_cmd);
  }

  bool HandleArrowKeys() {
    char next_char = getch();
    if (next_char != 91)
      return false;

    char arrow_char = getch();
    if (!CanMoveMode())
      return false;

    switch (arrow_char) {
    case 'D':
      SendMoveCommand(0.0, 0.0, -ANGULAR_VELOCITY_Z);
      printf("左转: %.2f rad/s\n", cmd_wz_);
      return true;
    case 'C':
      SendMoveCommand(0.0, 0.0, ANGULAR_VELOCITY_Z);
      printf("右转: %.2f rad/s\n", cmd_wz_);
      return true;
    case 'A':
      SendMoveCommand(LINEAR_VELOCITY_X, 0.0, 0.0);
      printf("前进: %.2f m/s\n", cmd_vx_);
      return true;
    case 'B':
      SendMoveCommand(-LINEAR_VELOCITY_X, 0.0, 0.0);
      printf("后退: %.2f m/s\n", cmd_vx_);
      return true;
    default:
      return false;
    }
  }

  void KeyboardControlThread() {
    printf("键盘控制已启动：\n");
    printf("1: RECOVERY_STAND | 2: STAND_DOWN | 3: DAMP | 4: RL_WALK | 5: DEVELOPMENT\n");
    printf("移动键: 方向键\n");
    printf("左右横移: H/J\n");
    printf("QAZ 调站高: q增加  a减小  z归零\n");
    printf("WSX 调横滚: w增加  s减小  x归零\n");
    printf("EDC 调俯仰: e增加  d减小  c归零\n");
    printf("V: 退出程序\n");

    while (keyboard_running) {
      char key = getch();
      switch (key) {
      case '1': TEST_MODE = mode_recovery_stand; SendStopCommand(); break;
      case '2': TEST_MODE = mode_stand_down; SendStopCommand(); break;
      case '3': TEST_MODE = mode_damp; SendStopCommand(); break;
      case '4': TEST_MODE = mode_rl_walk; SendStopCommand(); break;
      case '5': TEST_MODE = mode_development; SendStopCommand(); break;

      case 'q':
      case 'Q':
        if (CanPoseMode()) {
          body_height_cmd += BODY_HEIGHT_STEP;
          if (body_height_cmd > 0.20f) body_height_cmd = 0.20f;
          ApplyPose();
        }
        break;
      case 'a':
      case 'A':
        if (CanPoseMode()) {
          body_height_cmd -= BODY_HEIGHT_STEP;
          if (body_height_cmd < -1.00f) body_height_cmd = -1.00f;
          ApplyPose();
        }
        break;
      case 'w':
      case 'W':
        if (CanPoseMode()) {
          roll_cmd += EULER_STEP;
          if (roll_cmd > 0.50f) roll_cmd = 0.50f;
          ApplyPose();
        }
        break;
      case 's':
      case 'S':
        if (CanPoseMode()) {
          roll_cmd -= EULER_STEP;
          if (roll_cmd < -0.50f) roll_cmd = -0.50f;
          ApplyPose();
        }
        break;
      case 'e':
      case 'E':
        if (CanPoseMode()) {
          pitch_cmd += EULER_STEP;
          if (pitch_cmd > 0.50f) pitch_cmd = 0.50f;
          ApplyPose();
        }
        break;
      case 'd':
      case 'D':
        if (CanPoseMode()) {
          pitch_cmd -= EULER_STEP;
          if (pitch_cmd < -0.50f) pitch_cmd = -0.50f;
          ApplyPose();
        }
        break;
      case 'z':
      case 'Z':
        if (CanPoseMode()) {
          body_height_cmd = 0.0f;
          ApplyPose();
        }
        break;
      case 'x':
      case 'X':
        if (CanPoseMode()) {
          roll_cmd = 0.0f;
          ApplyPose();
        }
        break;
      case 'c':
      case 'C':
        if (CanPoseMode()) {
          pitch_cmd = 0.0f;
          ApplyPose();
        }
        break;
      case 'h':
      case 'H':
        if (CanMoveMode()) {
          SendMoveCommand(0.0f, -LINEAR_VELOCITY_Y, 0.0f);
          printf("左移: %.2f m/s\n", cmd_vy_);
        }
        break;
      case 'j':
      case 'J':
        if (CanMoveMode()) {
          SendMoveCommand(0.0f, LINEAR_VELOCITY_Y, 0.0f);
          printf("右移: %.2f m/s\n", cmd_vy_);
        }
        break;
      case ' ':
        if (CanMoveMode())
          SendStopCommand();
        break;
      case 27:
        HandleArrowKeys();
        break;

      case 'v':
      case 'V':
        keyboard_running = false;
        TEST_MODE = mode_exit;
        SendStopCommand();
        break;

      default:
        break;
      }

      usleep(KEYBOARD_PERIOD_US);
    }
  }

  void CheckKeyRelease() {
    static int no_movement_count = 0;
    if (is_moving && CanMoveMode()) {
      no_movement_count++;
      if (no_movement_count > RELEASE_THRESHOLD) {
        SendStopCommand();
        no_movement_count = 0;
      }
    } else {
      no_movement_count = 0;
    }
  }

  void RobotControl() {
    static int last_mode = -1;
    const int current_mode = TEST_MODE.load();
    // 20Hz 保活：每次循环都显式保持 SDK 接管
    sport_client.EnableLCMControl();

    // 20Hz 连发模式命令
    switch (current_mode) {
    case mode_recovery_stand: sport_client.RecoveryStand(); break;
    case mode_stand_down: sport_client.StandDown(); break;
    case mode_damp: sport_client.Damp(); break;
    case mode_rl_walk: sport_client.RLWalk(); break;
    case mode_development: sport_client.Development(); break;
    default: break;
    }

    // 20Hz 连发运动/姿态命令（RL_WALK / DEVELOPMENT）
    if (CanMoveMode()) {
      sport_client.Move(cmd_vx_, cmd_vy_, cmd_wz_);
      sport_client.BodyHeight(body_height_cmd);
      sport_client.Euler(roll_cmd, pitch_cmd);
    }

    if (current_mode != last_mode) {
      printf("模式切换 -> %d\n", current_mode);
      last_mode = current_mode;
    }

    //if (CanMoveMode())
    //  CheckKeyRelease();
  }

  yobotics::robot::SportClient sport_client;
  float body_height_cmd = 0.0f;
  float roll_cmd = 0.0f;
  float pitch_cmd = 0.0f;
  float cmd_vx_ = 0.0f;
  float cmd_vy_ = 0.0f;
  float cmd_wz_ = 0.0f;
};

int main(int argc, char **argv) {
  (void)argc;
  (void)argv;

  Custom custom;
  std::thread keyboard_thread(&Custom::KeyboardControlThread, &custom);

  while (keyboard_running) {
    custom.RobotControl();
    usleep(40000);
  }

  if (keyboard_thread.joinable()) {
    keyboard_thread.join();
  }

  return 0;
}
