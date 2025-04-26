from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior

from .project import Project, load_project


class MainWindow(BoxLayout): pass

class SectionPanel(BoxLayout, RecycleDataViewBehavior): pass

class DisApp(App):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.main_panel: BoxLayout = None
    
    def build(self):
        window = MainWindow()
        self.main_panel = window.ids.main_panel
        self.load_regions()
        return window
    
    def load_regions(self):
        self.main_panel.clear_widgets()
        #for section in self.project.sections:
        print(len(self.project.sections))
        for i in range(30):
            section_panel = SectionPanel()
            self.main_panel.add_widget(section_panel)

def main(path: str, ep: int, org: int):
    project = load_project(path, ep, org)

    window = DisApp(project)
    window.run()