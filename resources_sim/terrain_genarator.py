from pathlib import Path


# ==================================================
# 路径配置（只改这里）
# ==================================================

# 原始 scene（里面包含机器人 include）
INPUT_XML = "robots/quad144w/scene.xml"

# 输出新地形
OUTPUT_XML = "robots/quad144w/scene_terrain.xml"


# ==================================================
# 楼梯参数（只改这里）
# ==================================================

START_X = 1.33          # 台阶起始位置

STEP_HEIGHT = 0.12 #0.16      # 每级高度（m）
STEP_DEPTH = 0.33       # 每级进深（x方向长度）
STEP_WIDTH = 1.75       # y方向半宽

NUM_STEPS = 8           # 楼梯级数

PLATFORM_LENGTH = 1.0   # 顶部平台长度

THICKNESS = 0.16        # 台阶厚度

FRICTION = "1.0 0.005 0.0001"
MATERIAL = MATERIAL = "floor_mat" #"wood"


def generate_stairs_xml(
    start_x=START_X,
    step_height=STEP_HEIGHT,
    step_depth=STEP_DEPTH,
    step_width=STEP_WIDTH,
    num_steps=NUM_STEPS,
    platform_length=PLATFORM_LENGTH,
    thickness=THICKNESS,
    friction=FRICTION,
    material=MATERIAL,
):
    """
    生成:
    上楼梯 -> 平台 -> 下楼梯
    """

    geom_list = []

    half_depth = step_depth / 2
    half_height = thickness / 2

    x = start_x

    # ==================================================
    # 上楼梯
    # ==================================================
    for i in range(num_steps):

        z_center = half_height + i * step_height

        geom = (
            f'<geom '
            f'pos="{x:.4f} 0.0 {z_center:.4f}" '
            f'type="box" '
            f'size="{half_depth:.4f} {step_width:.4f} {half_height:.4f}" '
            f'quat="1 0 0 0" '
            f'material="{material}" '
            f'friction="{friction}" />'
        )

        geom_list.append(geom)

        x += step_depth

    # ==================================================
    # 顶部平台
    # ==================================================
    top_z = half_height + (num_steps - 1) * step_height

    platform_half_length = platform_length / 2

    geom = (
        f'<geom '
        f'pos="{x + platform_half_length - half_depth:.4f} 0.0 {top_z:.4f}" '
        f'type="box" '
        f'size="{platform_half_length:.4f} {step_width:.4f} {half_height:.4f}" '
        f'quat="1 0 0 0" '
        f'material="{material}" '
        f'friction="{friction}" />'
    )

    geom_list.append(geom)

    x += platform_length

    # ==================================================
    # 下楼梯
    # ==================================================
    for i in reversed(range(num_steps)):

        z_center = half_height + i * step_height

        geom = (
            f'<geom '
            f'pos="{x:.4f} 0.0 {z_center:.4f}" '
            f'type="box" '
            f'size="{half_depth:.4f} {step_width:.4f} {half_height:.4f}" '
            f'quat="1 0 0 0" '
            f'material="{material}" '
            f'friction="{friction}" />'
        )

        geom_list.append(geom)

        x += step_depth

    return "\n".join(geom_list)


def main():

    # ==========================
    # 读取原始场景
    # ==========================
    xml_text = Path(INPUT_XML).read_text()

    # ==========================
    # 生成楼梯
    # ==========================
    stairs_xml = generate_stairs_xml()

    # ==========================
    # 插入到 </worldbody> 前
    # ==========================
    xml_text = xml_text.replace(
        "</worldbody>",
        f"\n{stairs_xml}\n</worldbody>"
    )

    # ==========================
    # 保存新 xml
    # ==========================
    Path(OUTPUT_XML).write_text(xml_text)

    print("=" * 50)
    print("terrain generated")
    print(f"input : {INPUT_XML}")
    print(f"output: {OUTPUT_XML}")
    print("=" * 50)


if __name__ == "__main__":
    main()