from cleanroomx.gui_geometry import configure_toplevel_geometry


class _Window:
    def __init__(self, screen_width: int, screen_height: int):
        self._screen_width = screen_width
        self._screen_height = screen_height
        self.geometry_value = None
        self.minimum = None

    def winfo_screenwidth(self):
        return self._screen_width

    def winfo_screenheight(self):
        return self._screen_height

    def geometry(self, value):
        self.geometry_value = value

    def minsize(self, width, height):
        self.minimum = (width, height)


def test_dialog_geometry_preserves_requested_size_when_display_allows_it():
    window = _Window(1920, 1080)

    fitted = configure_toplevel_geometry(
        window,
        width=1480,
        height=780,
        min_width=1080,
        min_height=580,
    )

    assert fitted == (1480, 780, 1080, 580)
    assert window.geometry_value == "1480x780"
    assert window.minimum == (1080, 580)


def test_dialog_geometry_clamps_size_and_minimum_to_small_display():
    window = _Window(1024, 600)

    fitted = configure_toplevel_geometry(
        window,
        width=1480,
        height=780,
        min_width=1080,
        min_height=680,
    )

    assert fitted == (1024, 600, 1024, 600)
    assert window.geometry_value == "1024x600"
    assert window.minimum == (1024, 600)


def test_dialog_geometry_handles_invalid_zero_display_extent_defensively():
    window = _Window(0, 0)

    fitted = configure_toplevel_geometry(
        window,
        width=680,
        height=430,
        min_width=520,
        min_height=320,
    )

    assert fitted == (1, 1, 1, 1)
    assert window.geometry_value == "1x1"
    assert window.minimum == (1, 1)
