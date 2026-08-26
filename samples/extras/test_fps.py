from ursina import *
from AFPC import AdvancedFirstPersonController

app = Ursina()

# ground
ground = Entity(
    model='plane',
    scale=100,
    collider='box',
    texture='white_cube',
    texture_scale=(50, 50),
    color=color.dark_gray
)

# walls for wall-run testing
wall1 = Entity(
    model='cube',
    scale=(1, 10, 30),
    position=(5, 5, 0),
    collider='box',
    color=color.gray
)

wall2 = Entity(
    model='cube',
    scale=(1, 10, 30),
    position=(-5, 5, 0),
    collider='box',
    color=color.gray
)

# player
player = AdvancedFirstPersonController(
    position=(0, 20, 0),
    debug=True
)

Sky()
app.run()
