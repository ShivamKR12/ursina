"""
AdvancedFirstPersonController (single-file prefab)
Features: sprint, crouch, slide, dash, double jump, wall-run (horizontal), hookshot (pull-to-point),
          flying (toggle), gliding.
Minimal production-like code with configuration flags and a simple text indicator (no UI).

Usage:
    from ursina.prefabs.advanced_first_person import AdvancedFirstPersonController
    player = AdvancedFirstPersonController()
Or add via the editor/ClassSpawner using class name "AdvancedFirstPersonController".

Notes:
- This prefab is a high-level prototype: it uses raycasts for ground/wall checks and manual velocity integration.
- Tuning values are exposed as attributes on the instance.
- Hookshot is a fast pull-to-point (no rope physics).
"""

from ursina import (
    Entity, camera, mouse, held_keys, Vec3, time, raycast, distance, Text,
    application, scene, color, invoke
)


class AdvancedFirstPersonController(Entity):
    def __init__(self,
                 name='advanced_fps',
                 position=(0, 1, 0),
                 height=1.8,
                 speed=10,
                 mouse_sensitivity = 40,
                 sprint_speed=25,
                 jump_height=1.2,
                 gravity=4,
                 max_jumps=2,
                 dash_distance=5,
                 dash_cooldown=1.0,
                 dash_time=0.12,
                 slide_force=6,
                 slide_time=0.7,
                 slide_speed_multiplier=1.5,
                 wallrun_time=1.0,
                 wallrun_speed=6,
                 wallrun_gravity=0.5,
                 hookshot_range=40,
                 hookshot_speed=50,
                 fly_speed=8,
                 glide_gravity_mult=0.5,
                 stamina_max=3.0,
                 stamina_drain_rate=1.0,
                 stamina_regen_rate=0.75,
                 enable_sprint=True,
                 enable_crouch=True,
                 enable_slide=True,
                 enable_dash=True,
                 enable_double_jump=True,
                 enable_wallrun=True,
                 enable_hookshot=True,
                 enable_fly=True,
                 enable_glide=True,
                 debug=False,
                 **kwargs):
        super().__init__(name=name, position=position, **kwargs)

        # config
        self.base_height = height
        self.camera_pivot = Entity(parent=self, y=self.base_height)
        # attach global camera to pivot
        camera.parent = self.camera_pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)

        # movement params
        self.walk_speed = speed
        self.sprint_speed = sprint_speed
        self.jump_height = jump_height
        self.gravity = gravity
        self.max_jumps = max_jumps
        self.dash_distance = dash_distance
        self.dash_cooldown = dash_cooldown
        self._dash_time = dash_time
        self.slide_force = slide_force
        self.slide_time = slide_time
        self.slide_speed_multiplier = slide_speed_multiplier
        self.wallrun_time = wallrun_time
        self.wallrun_speed = wallrun_speed
        self.wallrun_gravity = wallrun_gravity
        self.hookshot_range = hookshot_range
        self.hookshot_speed = hookshot_speed
        self.fly_speed = fly_speed
        self.glide_gravity_mult = glide_gravity_mult

        # stamina
        self.stamina_max = stamina_max
        self.stamina = stamina_max
        self.stamina_drain_rate = stamina_drain_rate
        self.stamina_regen_rate = stamina_regen_rate

        # feature toggles
        self.enable_sprint = enable_sprint
        self.enable_crouch = enable_crouch
        self.enable_slide = enable_slide
        self.enable_dash = enable_dash
        self.enable_double_jump = enable_double_jump
        self.enable_wallrun = enable_wallrun
        self.enable_hookshot = enable_hookshot
        self.enable_fly = enable_fly
        self.enable_glide = enable_glide

        # runtime state
        self.velocity = Vec3(0, 0, 0)
        self.grounded = False
        self.jumps_done = 0
        self.flying = False
        self.sliding = False
        self.slide_timer = 0
        self.dashing = False
        self.dash_timer = 0
        self.dash_cooldown_timer = 0
        self.wallrunning = False
        self.wallrun_timer = 0
        self.hookshotting = False
        self.hook_target = None
        self.hook_dir = None
        self.double_jump_available = True
        self.debug = debug

        # input/look
        self.mouse_sensitivity = mouse_sensitivity
        self.pitch = 0
        mouse.locked = True

        # simple indicator (text)
        self.indicator = Text(parent=camera.ui, text='', position=(-0.85, 0.45), origin=(0, 0), scale=1.2, color=color.white)

        # small collision/check offsets
        self.ground_check_dist = 0.25 + 0.01
        self.wall_check_dist = 0.8

        # safety: ensure entity is updatable even if spawned externally
        self.enabled = True
        self.ignore = False
        self.ignore_input = False

    # ---- helpers ----
    def _forward_direction(self):
        forward = Vec3(0, 0, 1)
        forward = self.camera_pivot.forward
        forward.y = 0
        return forward.normalized()

    def _right_direction(self):
        right = self.camera_pivot.right
        right.y = 0
        return right.normalized()

    def _check_ground(self):
        # raycast down from pivot origin a little below feet
        start = self.world_position + Vec3(0, 0.1, 0)
        hit = raycast(start, Vec3(0, -1, 0), distance=self.base_height + 0.2, ignore=[self, camera, ], traverse_target=scene)
        if hit.hit:
            # consider grounded if close to ground
            ground_dist = hit.distance
            self.grounded = ground_dist <= (self.ground_check_dist + 0.01)
            return True
        self.grounded = False
        return False

    def _check_wall(self):
        # checks both sides for a wall near the player (used for basic wall-run)
        fwd = self._forward_direction()
        right = self._right_direction()
        left_hit = raycast(self.world_position, -right, distance=self.wall_check_dist, ignore=[self, camera], traverse_target=scene)
        right_hit = raycast(self.world_position, right, distance=self.wall_check_dist, ignore=[self, camera], traverse_target=scene)
        if left_hit.hit:
            return ('left', left_hit)
        if right_hit.hit:
            return ('right', right_hit)
        return (None, None)

    def _ground_jump_velocity(self):
        # approximate jump velocity for desired height under current gravity
        # v = sqrt(2 * g * h)
        return (2 * self.gravity * self.jump_height) ** 0.5

    def on_enable(self):
        mouse.locked = True

    def on_disable(self):
        mouse.locked = False

    def on_window_ready(self):
        mouse.locked = True

    # ---- input handlers ----
    def input(self, key):
        if key == 'escape':
            application.quit()

        if key == 'f' and self.enable_fly:
            # toggle fly
            self.flying = not self.flying
            # when toggling to flying, clear vertical velocity
            if self.flying:
                self.velocity.y = 0

        if key == 'space':
            # jump
            if self.flying:
                return  # in flying mode space reserved maybe for up movement handled in update
            if self.grounded:
                self.velocity.y = self._ground_jump_velocity()
                self.jumps_done = 1
                self.double_jump_available = True
            else:
                if self.enable_double_jump and self.double_jump_available:
                    self.velocity.y = self._ground_jump_velocity()
                    self.double_jump_available = False
                    self.jumps_done += 1
        if key == 'q' and self.enable_dash and not self.dashing and self.dash_cooldown_timer <= 0:
            # dash in movement direction
            self._start_dash()

        if key == 'e' and self.enable_hookshot and not self.hookshotting:
            self._try_hookshot()

    # ---- actions ----
    def _start_dash(self):
        dir = Vec3(0, 0, 0)
        if held_keys['w']:
            dir += self._forward_direction()
        if held_keys['s']:
            dir -= self._forward_direction()
        if held_keys['a']:
            dir -= self._right_direction()
        if held_keys['d']:
            dir += self._right_direction()
        if dir == Vec3(0, 0, 0):
            dir = self._forward_direction()
        self.dashing = True
        self.dash_timer = self._dash_time
        self.dash_cooldown_timer = self.dash_cooldown
        self.velocity += dir.normalized() * (self.dash_distance / max(self._dash_time, 0.001))

    def _try_hookshot(self):
        origin = camera.world_position
        direction = camera.forward
        hit = raycast(origin, direction, distance=self.hookshot_range, ignore=[self, camera], traverse_target=scene)
        if hit.hit:
            self.hookshotting = True
            self.hook_target = hit.world_point
            self.hook_dir = (self.hook_target - self.world_position).normalized()
            # cancel vertical velocity for deterministic pull
            self.velocity = Vec3(0, 0, 0)

    # ---- wall-run helpers ----
    def _start_wallrun(self, wall_normal):
        self.wallrunning = True
        self.wallrun_timer = self.wallrun_time
        # push player slightly along wall forward vector
        # forward vector projected along wall
        forward = self._forward_direction()
        along_wall = (forward - wall_normal * forward.dot(wall_normal)).normalized()
        self.velocity = along_wall * self.wallrun_speed
        # small upwards boost to stay on wall
        self.velocity.y = 1.2

    def _stop_wallrun(self):
        self.wallrunning = False
        self.wallrun_timer = 0

    # ---- update loop ----
    def update(self):
        dt = time.dt

        # mouse look
        mvel = getattr(mouse, 'velocity', (0, 0))
        # mvel is often a Vec2; handle gracefully
        mx = mvel[0] if len(mvel) > 0 else 0
        my = mvel[1] if len(mvel) > 1 else 0
        self.rotation_y += mx * self.mouse_sensitivity
        self.pitch -= my * self.mouse_sensitivity
        self.pitch = max(-89, min(89, self.pitch))
        camera.rotation_x = self.pitch

        # ground/wall checks
        self._check_ground()
        wall_side, wall_hit = self._check_wall()

        # update timers
        if self.dash_cooldown_timer > 0:
            self.dash_cooldown_timer -= dt
        if self.dashing:
            self.dash_timer -= dt
            if self.dash_timer <= 0:
                self.dashing = False

        # hookshot
        if self.hookshotting:
            to_target = self.hook_target - self.world_position
            dist_to_target = to_target.length()
            if dist_to_target < 1.0:
                # reached
                self.hookshotting = False
                self.hook_target = None
            else:
                move = self.hook_dir * self.hookshot_speed * dt
                # avoid overshoot
                if move.length() > dist_to_target:
                    move = to_target
                self.world_position += move
                return  # while hookshotting, skip other movement

        # flying mode (free flight)
        if self.flying:
            move_dir = Vec3(0, 0, 0)
            if held_keys['w']:
                move_dir += self._forward_direction()
            if held_keys['s']:
                move_dir -= self._forward_direction()
            if held_keys['a']:
                move_dir -= self._right_direction()
            if held_keys['d']:
                move_dir += self._right_direction()
            if held_keys['space']:
                move_dir += Vec3(0, 1, 0)
            if held_keys['shift']:
                move_dir -= Vec3(0, 1, 0)
            if move_dir != Vec3(0, 0, 0):
                self.world_position += move_dir.normalized() * self.fly_speed * dt
            return

        # movement input
        move_dir = Vec3(0, 0, 0)
        if held_keys['w']:
            move_dir += self._forward_direction()
        if held_keys['s']:
            move_dir -= self._forward_direction()
        if held_keys['a']:
            move_dir -= self._right_direction()
        if held_keys['d']:
            move_dir += self._right_direction()

        # sprint & stamina
        sprinting = False
        desired_speed = self.walk_speed
        if self.enable_sprint and held_keys['shift'] and self.stamina > 0 and move_dir.length() > 0.1:
            sprinting = True
            desired_speed = self.sprint_speed

        if sprinting:
            self.stamina -= self.stamina_drain_rate * dt
            if self.stamina < 0:
                self.stamina = 0
                sprinting = False
        else:
            if self.grounded:
                self.stamina = min(self.stamina + self.stamina_regen_rate * dt, self.stamina_max)

        # sliding
        if self.enable_slide and self.enable_crouch and held_keys['control'] and sprinting and self.grounded and not self.sliding:
            # start slide
            self.sliding = True
            self.slide_timer = self.slide_time
            forward = self._forward_direction()
            self.velocity += forward * self.slide_force

        if self.sliding:
            self.slide_timer -= dt
            desired_speed = max(desired_speed * self.slide_speed_multiplier, desired_speed)
            # friction style decay
            self.velocity.x *= (1 - min(dt * 6, 0.9))
            self.velocity.z *= (1 - min(dt * 6, 0.9))
            if self.slide_timer <= 0:
                self.sliding = False

        # wall-run conditions
        if self.enable_wallrun and not self.grounded and wall_side and not self.wallrunning:
            # basic condition: near a wall and moving forward
            if move_dir.length() > 0.1 and held_keys['w']:
                # start wallrun
                wall_normal = wall_hit.normal if wall_hit else Vec3(0, 0, 0)
                self._start_wallrun(wall_normal)

        if self.wallrunning:
            self.wallrun_timer -= dt
            # keep wallrun for limited time
            if self.wallrun_timer <= 0:
                self._stop_wallrun()
            else:
                # apply reduced gravity while wallrunning
                self.velocity.y -= self.gravity * self.wallrun_gravity * dt

        # apply gravity
        if not self.grounded and not self.wallrunning:
            # gliding
            if self.enable_glide and held_keys['space'] and self.velocity.y < 0:
                self.velocity.y -= self.gravity * self.glide_gravity_mult * dt
            else:
                self.velocity.y -= self.gravity * dt
        else:
            # grounded: zero small downward velocity
            if self.grounded and self.velocity.y < 0:
                self.velocity.y = 0
                self.double_jump_available = True
                self.jumps_done = 0

        # acceleration toward desired horizontal velocity
        horizontal = Vec3(self.velocity.x, 0, self.velocity.z)
        target_h = move_dir.normalized() * desired_speed if move_dir.length() > 0 else Vec3(0, 0, 0)

        accel = 20.0
        horizontal = horizontal + (target_h - horizontal) * min(accel * dt, 1)
        self.velocity.x, self.velocity.z = horizontal.x, horizontal.z

        # update position
        self.world_position += self.velocity * dt

        # dash cooldown handled above; dashing state affects velocity but no extra behavior needed here

        # crouch camera height
        if self.enable_crouch and held_keys['control']:
            target_height = self.base_height * 0.5
        else:
            target_height = self.base_height
        # lerp camera pivot height smoothly
        self.camera_pivot.y = self.camera_pivot.y + (target_height - self.camera_pivot.y) * min(10 * dt, 1)

        # update indicator
        state = 'flying' if self.flying else ('hookshot' if self.hookshotting else ('wallrun' if self.wallrunning else ('sliding' if self.sliding else ('dashing' if self.dashing else ('sprinting' if sprinting else ('grounded' if self.grounded else 'air'))))))
        self.indicator.text = f'{state} | stamina: {self.stamina:.1f}/{self.stamina_max}'

    def destroy(self):
        # cleanup camera parent if this controller owns it
        try:
            # reset camera parent to scene root
            camera.parent = scene
            camera.position = (0, 0, 0)
            camera.rotation = (0, 0, 0)
        except Exception:
            pass
        super().destroy()