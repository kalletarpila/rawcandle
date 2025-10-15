import flet as ft

class RawCandleApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.setup_page()
        self.setup_routing()
        
        # Komponentin tilan hallinta
        self.name_field = ft.TextField(label="Your name", width=250)
        self.greeting = ft.Text(value="", size=20, weight=ft.FontWeight.BOLD)
        
        # Aloita etusivulta
        self.page.go("/")

    def setup_page(self):
        """Asettaa sivun perusasetukset"""
        self.page.title = "RawCandle - Flet Web App"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_width = 800
        self.page.window_height = 600
        
    def setup_routing(self):
        """Asettaa reitityksen"""
        self.page.on_route_change = self.route_change
        
    def create_appbar(self):
        """Luo yläpalkin navigaatiolla"""
        return ft.AppBar(
            leading=ft.Icon(ft.Icons.WHATSHOT),
            leading_width=40,
            title=ft.Text("RawCandle", size=20, weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor=ft.Colors.ORANGE_300,
            actions=[
                ft.IconButton(
                    ft.Icons.HOME,
                    tooltip="Home",
                    on_click=lambda _: self.page.go("/")
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS,
                    tooltip="Settings", 
                    on_click=lambda _: self.page.go("/settings")
                ),
            ],
        )

    def create_home_view(self):
        """Luo etusivun näkymän"""
        return ft.View(
            "/",
            [
                self.create_appbar(),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "🌕 Welcome to RawCandle!", 
                                size=32, 
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ORANGE_700
                            ),
                            ft.Text(
                                "A modern Flet web application", 
                                size=16,
                                color=ft.Colors.GREY_600
                            ),
                            ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                            
                            # Alkuperäinen demo-toiminnallisuus
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column([
                                        ft.Text("Interactive Demo", size=20, weight=ft.FontWeight.BOLD),
                                        self.name_field,
                                        ft.ElevatedButton(
                                            "Say Hello", 
                                            icon=ft.Icons.WAVING_HAND,
                                            on_click=self.say_hello
                                        ),
                                        self.greeting,
                                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                    padding=20,
                                ),
                                elevation=3,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=20,
                    ),
                    padding=40,
                    expand=True,
                )
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def create_settings_view(self):
        """Luo asetusten näkymän"""
        return ft.View(
            "/settings",
            [
                self.create_appbar(),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "⚙️ Settings", 
                                size=32, 
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ORANGE_700
                            ),
                            ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                            
                            # Asetusten kortit
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column([
                                        ft.ListTile(
                                            leading=ft.Icon(ft.Icons.PALETTE),
                                            title=ft.Text("Theme"),
                                            subtitle=ft.Text("Customize app appearance"),
                                            trailing=ft.Switch(
                                                value=self.page.theme_mode == ft.ThemeMode.DARK,
                                                on_change=self.toggle_theme
                                            ),
                                        ),
                                        ft.Divider(),
                                        ft.ListTile(
                                            leading=ft.Icon(ft.Icons.NOTIFICATIONS),
                                            title=ft.Text("Notifications"),
                                            subtitle=ft.Text("Enable app notifications"),
                                            trailing=ft.Switch(value=True),
                                        ),
                                        ft.Divider(),
                                        ft.ListTile(
                                            leading=ft.Icon(ft.Icons.INFO),
                                            title=ft.Text("About"),
                                            subtitle=ft.Text("RawCandle v1.0.0 - Built with Flet"),
                                        ),
                                    ]),
                                    padding=10,
                                ),
                                elevation=3,
                            ),
                            
                            ft.Container(height=20),
                            
                            ft.ElevatedButton(
                                "Back to Home",
                                icon=ft.Icons.HOME,
                                on_click=lambda _: self.page.go("/")
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=20,
                    ),
                    padding=40,
                    expand=True,
                )
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def route_change(self, route):
        """Käsittelee reitityksen muutokset"""
        self.page.views.clear()
        
        # Lisää näkymä reitin perusteella
        if self.page.route == "/" or self.page.route == "/home":
            self.page.views.append(self.create_home_view())
        elif self.page.route == "/settings":
            self.page.views.append(self.create_settings_view())
        else:
            # 404 - palaa etusivulle
            self.page.go("/")
            
        self.page.update()

    def say_hello(self, e):
        """Alkuperäinen demo-toiminto"""
        if self.name_field.value.strip():
            self.greeting.value = f"Hello, {self.name_field.value}! 👋"
        else:
            self.greeting.value = "Please enter your name first! 😊"
        self.page.update()

    def toggle_theme(self, e):
        """Vaihtaa teeman tumman ja vaalean välillä"""
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.page.theme_mode = ft.ThemeMode.DARK
        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.update()

def main(page: ft.Page):
    """Pääfunktio - luo sovelluksen instanssin"""
    app = RawCandleApp(page)

ft.app(target=main, port=8080, view=None)
