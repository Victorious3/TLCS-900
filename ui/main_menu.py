import sys
from abc import ABC, abstractmethod
from threading import Thread

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.core.window import Window
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
        MenuItem("exit", "Close Window")
    ]),
    MenuItem(None, "Analyze", [
        MenuItem("functions", "Functions")
    ])
]

class MainMenuHandler(MenuHandler):
    def on_select(self, item):
        def interval(dt):
            Window.set_system_cursor("wait")
            app().set_hover()

        def analyze():
            wait = Clock.schedule_interval(interval, 0)
            app().project.analyze_functions()
            wait.cancel()
            Clock.schedule_once(finish, 0)

        def finish(dt):
            sys.setswitchinterval(previ)
            Window.set_system_cursor("arrow")
            app().open_function_list()

        if item == "functions":
            if app().project.functions is None:
                previ = sys.getswitchinterval()
                sys.setswitchinterval(0.0005)
                Thread(target=analyze, daemon=True).start()
            else: app().open_function_list()

        app().app_menu.close_all()
        
main_menu_handler = MainMenuHandler()

if sys.platform == "darwin":
    import objc
    from Foundation import NSObject
    from AppKit import NSApp, NSApplication, NSMenu, NSMenuItem

    NSMenuDelegate = objc.protocolNamed("NSMenuDelegate")

    class NativeMenuDelegate(NSObject, protocols=[NSMenuDelegate]):
        def initWithHandler_(self, handler):
            self = objc.super(NativeMenuDelegate, self).init()
            if self is None: return None
            self.handler = handler
            return self

        @objc.selector
        def menuDidClose_(self, menu):
            Clock.schedule_once(lambda dt: self.handler.on_close(), 0)

    class NativeMenuHandler(NSObject):
        def initWithItem_handler_(self, item, handler):
            self = objc.super(NativeMenuHandler, self).init()
            if self is None: return None
            self.item = item
            self.handler = handler
            return self
            
        @objc.selector
        def select_(self, sender):
            Clock.schedule_once(lambda dt: self.handler.on_select(self.item), 0)

    global_handlers = []

    def build_menu():
        app = NSApplication.sharedApplication()
        native_menu = NSApp.mainMenu()
        # Remove "Window" menu
        native_menu.removeItemAtIndex_(native_menu.numberOfItems() - 1)
        #delegate = NativeMenuDelegate.alloc().initWithHandler_(main_menu_handler)

        def build_rec(menu: MenuItem, parent: NSMenuItem):
            sub_menu = NSMenu.alloc().initWithTitle_(menu.text)
            for item in menu.child_menu:
                native_handler = NativeMenuHandler.alloc().initWithItem_handler_(item.id, main_menu_handler)
                global_handlers.append(native_handler)
                native_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    item.text, "select:", "")
                native_item.setTarget_(native_handler)
                if item.child_menu:
                    build_rec(item, native_item)
                sub_menu.addItem_(native_item)
            parent.setSubmenu_(sub_menu)

        for menu in main_menu:
            app_menu_item = NSMenuItem.alloc().init()
            build_rec(menu, app_menu_item)
            native_menu.addItem_(app_menu_item)

        #app.setMainMenu_(native_menu)
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
