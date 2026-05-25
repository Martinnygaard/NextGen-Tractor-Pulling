from scoreboard_display import run_display_hub


# Display hub 1 controls global matrix columns 0..2.
HUB_INDEX = 0

# Local matrix layout:
# [A][C][E]
# [B][D][F]
# Compensate for 90° CW hardware rotation by rotating matrices 270°.
ROTATIONS = [270, 270, 270, 270, 270, 270]


run_display_hub(HUB_INDEX, ROTATIONS)
