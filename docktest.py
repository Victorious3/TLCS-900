from kivy.app import App
from kivy.uix.label import Label

from ui.dock.dock import Dock, DockTab, Orientation


class TabbedPanelApp(App):
    def build(self):
        dock = Dock()

        def make_panel(index: int):
            panel = DockTab(text="Panel" + str(index))
            panel.add_widget(Label(text="Panel" + str(index)))
            return panel

        dock.add_panel(make_panel(1))
        dock.add_panel(make_panel(2))

        dock.split(make_panel(3))
        dock.split(make_panel(4), Orientation.VERTICAL)

        dock.add_panel(make_panel(5))

        return dock
    

if __name__ == "__main__":
    TabbedPanelApp().run()