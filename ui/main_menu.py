import sys
from abc import ABC, abstractmethod

from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy_garden.contextmenu import AppMenuTextItem, ContextMenu, ContextMenuTextItem, AbstractMenuItem

from .main import app

class MenuHandler(ABC):
    def on_close(self): pass
    @abstractmethod
    def on_select(self, item: str): pass

class MenuItem:
    def __init__(self, id: str, text: str, child_menu: list["MenuItem"] = None):
        self.id = id
        self.text = text
        self.child_menu = child_menu

main_menu = [
    MenuItem(None, "File", [
        MenuItem("open", "Open Project"),
        MenuItem("new", "New Project"),
        MenuItem("save", "Save"),
        MenuItem("exit", "Exit")
    ])
]
class MainMenuHandler(MenuHandler):
    def on_select(self, item):
        app().app_menu.close_all()
        
main_menu_handler = MainMenuHandler()

if sys.platform == "darwin":
    def build_menu():
        pass
else:
    def build_menu():
        def build_rec(menu_item: AbstractMenuItem, item: MenuItem):
            ctx_menu = ContextMenu()
            for child in item.child_menu:
                child_item = ContextMenuTextItem(text=child.text)
                if child.id:
                    child_item.bind(on_release=lambda i, id=child.id: main_menu_handler.on_select(id))
                if child.child_menu:
                    build_rec(child_item, child)

                ctx_menu.add_widget(child_item)

            menu_item.add_widget(ctx_menu)
            menu_item.submenu = ctx_menu
            ctx_menu._on_visible(False)

        app_menu = app().app_menu
        app_menu.on_cancel_handler_widget(None, None)

        for item in main_menu:
            menu_item = AppMenuTextItem(text=item.text)
            menu_item.padding = dp(10), 0
            if item.id:
                menu_item.bind(on_release=lambda i, id=item.id: main_menu_handler.on_select(id))
            app_menu.add_widget(menu_item)

            if item.child_menu:
                build_rec(menu_item, item)
