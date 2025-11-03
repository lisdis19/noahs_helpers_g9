import pygame

from core.engine import Engine
import core.constants as c


class ArkUI:
    def __init__(self, engine: Engine) -> None:
        pygame.init()

        self.engine = engine
        self.running = True
        self.paused = True
        self.clock = pygame.time.Clock()

        self.turn = 0

        self.screen = pygame.display.set_mode((c.SCREEN_WIDTH, c.SCREEN_HEIGHT))
        self.bg_color = c.BG_COLOR
        self.small_font = pygame.font.Font(None, 20)

    def write_at(self, line: str, coord: tuple[float, float]):
        text = self.small_font.render(line, True, (0, 0, 0))
        self.screen.blit(text, coord)

    def draw_grid(self):
        """Draw garden boundaries and grid."""
        border_rect = pygame.Rect(
            c.MARGIN_X, c.MARGIN_Y, c.LANDSCAPE_WIDTH, c.LANDSCAPE_HEIGHT
        )
        pygame.draw.rect(self.screen, (0, 0, 0), border_rect, 2)

        for i in range(c.NUM_GRID_LINES + 1):
            x = c.MARGIN_X + c.LANDSCAPE_WIDTH * i / c.NUM_GRID_LINES

            if i not in [0, c.NUM_GRID_LINES]:
                # only draw lines inside the grid
                pygame.draw.line(
                    self.screen,
                    c.GRID_COLOR,
                    (x, c.MARGIN_Y),
                    (x, c.MARGIN_Y + c.LANDSCAPE_HEIGHT),
                )

            line = "  X"
            if i:
                line = f"{int(c.X * i / c.NUM_GRID_LINES)}"
            self.write_at(line, (x - 10, c.MARGIN_Y - 20))

        for i in range(c.NUM_GRID_LINES + 1):
            y = c.MARGIN_Y + c.LANDSCAPE_HEIGHT * i / c.NUM_GRID_LINES

            if i not in [0, c.NUM_GRID_LINES]:
                pygame.draw.line(
                    self.screen,
                    c.GRID_COLOR,
                    (c.MARGIN_X, y),
                    (c.MARGIN_X + c.LANDSCAPE_WIDTH, y),
                )

            line = "  Y"
            if i:
                line = f"{int(c.Y * i / c.NUM_GRID_LINES)}"
            self.write_at(line, (c.MARGIN_X - 30, y - 5))

    def draw_objects(self):
        # draw ark
        ark_x, ark_y = self.engine.ark.position

        ark_x_px = c.LANDSCAPE_WEST_PX + c.LANDSCAPE_EAST_PX * ark_x / c.X
        ark_y_px = c.LANDSCAPE_NORTH_PX + c.LANDSCAPE_SOUTH_PX * ark_y / c.Y

        pygame.draw.circle(self.screen, c.ARK_COLOR, (ark_x_px, ark_y_px), c.ARK_RADIUS)

    def step_simulation(self):
        """Run one turn of simulation."""
        if self.turn < self.engine.time:
            self.engine.run_turn(self.turn)
            self.turn += 1
        else:
            self.paused = True

    def handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_q
            ):
                self.running = False

            elif event.type == pygame.KEYDOWN:
                # print(f"event {event.key}")
                if event.key == pygame.K_SPACE:
                    print(f"pressed space")
                    # self.paused = not self.paused
                elif event.key == pygame.K_RIGHT and self.paused:
                    print(f"pressed right")
                    # self.step_simulation()
                elif event.key == pygame.K_d:  # NEW: Toggle debug mode
                    print(f"toggle debug mode")
                #     self.debug_mode = not self.debug_mode

    def run(self) -> dict:
        while self.running:
            self.handle_events()

            if not self.paused:
                self.step_simulation()
                self.clock.tick(10)

            self.screen.fill(self.bg_color)
            self.draw_grid()
            self.draw_objects()
            # self.draw_info_panel()
            # self.draw_debug_info()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

        return {}
