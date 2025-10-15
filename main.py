import flet as ft

def main(page: ft.Page):
    page.title = "Flet Demo for Render.com"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    name = ft.TextField(label="Your name", width=250)
    greeting = ft.Text(value="", size=20, weight=ft.FontWeight.BOLD)

    def say_hello(e):
        greeting.value = f"Hello, {name.value}!"
        page.update()

    page.add(
        ft.Text("Welcome to the Flet demo app!", size=24, weight=ft.FontWeight.BOLD),
        name,
        ft.ElevatedButton("Say hello", on_click=say_hello),
        greeting,
    )

ft.app(target=main, port=8080, view=None)
