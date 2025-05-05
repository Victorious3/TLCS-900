import sys
from abc import ABC, abstractmethod
from kivy.clock import Clock
from kivy.core.window import Window

from .main import app

class MenuHandler(ABC):
    def on_close(self): pass
    @abstractmethod
    def on_select(self, item: str): pass

class MenuItem:
    def __init__(self, id: str, text: str):
        self.id = id
        self.text = text


if sys.platform == "darwin":
    # Native MacOS contex menu

    from AppKit import NSMenu, NSMenuItem, NSEvent
    from Foundation import NSObject

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

    def show_context_menu(handler: MenuHandler, menu_items: list[MenuItem]):
        menu = NSMenu.alloc().init() 
        delegate = NativeMenuDelegate.alloc().initWithHandler_(handler)

        handlers = []
        for item in menu_items:
            native_handler = NativeMenuHandler.alloc().initWithItem_handler_(item.id, handler)
            handlers.append(native_handler)
            native_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                item.text, "select:", "")
            native_item.setTarget_(native_handler)
            menu.addItem_(native_item)

        menu.setDelegate_(delegate)
        mouse_location = NSEvent.mouseLocation()
        menu.popUpMenuPositioningItem_atLocation_inView_(None, mouse_location, None)

else:
    from kivy_garden.contextmenu import ContextMenu, ContextMenuTextItem

    def show_context_menu(handler: MenuHandler, menu_items: list[MenuItem]):
        menu = ContextMenu(cancel_handler_widget=app().window)
        for item in menu_items:
            def on_release(id):
                handler.on_select(id)
                handler.on_close()
                menu.hide()
                app().window.remove_widget(menu)
            
            widget = ContextMenuTextItem(text = item.text)
            widget.bind(on_release=lambda x, id=item.id: on_release(id))
            widget.label.texture_update()
            menu.add_item(widget)
        
        app().window.add_widget(menu)
        menu.show(*app().root_window.mouse_pos)

