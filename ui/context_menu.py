import sys, ctypes, os
from kivy import __path__ as kivy_path

from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.metrics import Metrics
from kivy.clock import Clock

from .main import app
from .main_menu import MenuItem, MenuHandler

# Construct path to Kivy's bundled SDL2
#kivy_base = kivy_path[0]
#sdl_path = os.path.join(kivy_base, '.dylibs', 'SDL2')
#sdl = ctypes.CDLL(sdl_path)

class ContextMenuBehavior(Widget):
    menu_triggered = False

    def trigger_context_menu(self, touch) -> bool:
        return False

    def on_touch_down(self, touch):
        if touch.button == "right" and sys.platform == "darwin":
            # Hack for macos
            res = self.trigger_context_menu(touch)

            #sx = int(touch.sx * app().window.width / Metrics.density)
            #sy = int((app().window.height - touch.sy * app().window.height) / Metrics.density)
            #Window.dispatch("on_mouse_up", sx, sy, touch.button, ["pos", "button"])
            #ContextMenuBehavior.menu_triggered = True
            return res
        return super().on_touch_down(touch)
    
    def on_touch_up(self, touch):
        if touch.button == "right" and sys.platform != "darwin":
            return self.trigger_context_menu(touch) 
        return super().on_touch_up(touch)
    
    @classmethod
    def on_mouse_up(cls, window, x, y, button, modifiers):
        #print("mouse up", x, y, button)
        #if cls.menu_triggered:
        #    Window.dispatch("on_mouse_down", x, y, button, modifiers)
        #    cls.menu_triggered = False
        pass

    @classmethod
    def on_mouse_down(cls, window, x, y, button, modifiers):
        #print("mouse down", x, y, button)
        #cls.menu_triggered = False
        pass


if sys.platform == "darwin":
    # Native MacOS context menu

    import objc
    from AppKit import NSMenu, NSMenuItem, NSEvent
    from .main_menu import NativeMenuDelegate, NativeMenuHandler

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
        menu._setup_hover_timer()
        menu.show(*app().root_window.mouse_pos)

