from kivy.app import App
from kivy.uix.label import Label

from ui.dock.dock import Dock, DockTab, Orientation

from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

class TabbedPanelApp(App):
    def build(self):
        dock = Dock()

        def make_panel(index: int, source = None):
            text = "Panel" + str(index) + ("#" * index)
            panel = DockTab(text=text, closeable=(index % 2 == 0), source=source)
            panel.add_widget(Label(text=text))
            return panel

        dock.add_tab(make_panel(1, source="ui/resources/code-listing.png"))
        dock.add_tab(make_panel(2, source="ui/resources/graph.png"))
        dock.add_tab(make_panel(3))

        dock.split(make_panel(4))
        dock.split(make_panel(5), Orientation.VERTICAL)

        dock.add_tab(make_panel(6))

        return dock
    

if __name__ == "__main__":
    TabbedPanelApp().run()