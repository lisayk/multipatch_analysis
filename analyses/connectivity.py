"""
Prototype code for analyzing connectivity and synaptic properties between cell classes.


"""

from __future__ import print_function, division

from collections import OrderedDict
import numpy as np
import pyqtgraph as pg
from multipatch_analysis.database import database as db
from multipatch_analysis.connectivity import query_pairs, ConnectivityAnalyzer
from multipatch_analysis.connection_strength import ConnectionStrength, get_amps, get_baseline_amps
from multipatch_analysis.morphology import Morphology
from multipatch_analysis import constants
from multipatch_analysis.cell_class import CellClass, classify_cells, classify_pairs
from multipatch_analysis.ui.graphics import MatrixItem


class MainWindow(pg.QtGui.QWidget):
    def __init__(self):
        pg.QtGui.QWidget.__init__(self)
        self.layout = pg.QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.h_splitter = pg.QtGui.QSplitter()
        self.h_splitter.setOrientation(pg.QtCore.Qt.Horizontal)
        self.layout.addWidget(self.h_splitter, 0, 0)
        self.filter_control_panel = FilterControlPanel()
        self.h_splitter.addWidget(self.filter_control_panel)
        self.matrix_widget = MatrixWidget()
        self.h_splitter.addWidget(self.matrix_widget)
        self.v_splitter = pg.QtGui.QSplitter()
        self.v_splitter.setOrientation(pg.QtCore.Qt.Vertical)
        self.h_splitter.addWidget(self.v_splitter)
        self.scatter_plot = ScatterPlot()
        self.trace_plot = TracePlot()
        self.v_splitter.addWidget(self.scatter_plot)
        self.v_splitter.addWidget(self.trace_plot)

class FilterControlPanel(pg.QtGui.QWidget):
    def __init__(self):
        pg.QtGui.QWidget.__init__(self)
        self.layout = pg.QtGui.QVBoxLayout()
        self.setLayout(self.layout)
        self.update_button = pg.QtGui.QPushButton("Update Matrix")
        self.layout.addWidget(self.update_button)
        self.analyzer_list = pg.QtGui.QListWidget()
        self.layout.addWidget(self.analyzer_list)
        self.project_list = pg.QtGui.QListWidget()
        self.layout.addWidget(self.project_list)
        
        self.analyzers = {'Connectivity': ConnectivityAnalyzer}
        for analyzer in self.analyzers.keys():
            analyzer_item = pg.QtGui.QListWidgetItem(analyzer)
            analyzer_item.setFlags(analyzer_item.flags() | pg.QtCore.Qt.ItemIsUserCheckable)
            analyzer_item.setCheckState(pg.QtCore.Qt.Unchecked)
            self.analyzer_list.addItem(analyzer_item)

        s = db.Session()
        projects = s.query(db.Experiment.project_name).distinct().all()
        for record in projects:
            project = record[0]
            project_item = pg.QtGui.QListWidgetItem(project)
            project_item.setFlags(project_item.flags() | pg.QtCore.Qt.ItemIsUserCheckable)
            project_item.setCheckState(pg.QtCore.Qt.Unchecked)
            self.project_list.addItem(project_item)

    def selected_project_names(self):
        n_projects = self.project_list.count()
        project_names = []
        for n in range(n_projects):
            project_item = self.project_list.item(n)
            check_state = project_item.checkState()
            if check_state == pg.QtCore.Qt.Checked:
                project_names.append(str(project_item.text()))

        return project_names

    def selected_analyzer(self):
        n_analyzers = self.analyzer_list.count()
        analyzer = []
        for n in range(n_analyzers):
            analyzer_item = self.analyzer_list.item(n)
            check_state = analyzer_item.checkState()
            if check_state == pg.QtCore.Qt.Checked:
                analyzer.append(str(analyzer_item.text()))
        if len(analyzer) != 1:
            raise Exception ("Must select one and only one Matrix Analyzer")

        return analyzer

class MatrixWidget(pg.GraphicsLayoutWidget):
    sigClicked = pg.QtCore.Signal(object, object, object, object) # self, matrix_widget, row, col
    def __init__(self):
        pg.GraphicsLayoutWidget.__init__(self)
        self.setRenderHints(self.renderHints() | pg.QtGui.QPainter.Antialiasing)
        v = self.addViewBox()
        v.setBackgroundColor('w')
        v.setAspectLocked()
        v.invertY()
        self.view_box = v
        self.matrix = None

    def set_matrix_data(self, text, fgcolor, bgcolor, border_color, rows, cols, size=50, header_color='k'):
        if self.matrix is not None:
            self.view_box.removeItem(self.matrix)

        self.matrix = MatrixItem(text=text, fgcolor=fgcolor, bgcolor=bgcolor, border_color=border_color,
                    rows=rows, cols=rows, size=50, header_color='k')
        self.matrix.sigClicked.connect(self.matrix_element_clicked)
        self.view_box.addItem(self.matrix)

    def matrix_element_clicked(self, matrix_widget, event, row, col):
        self.sigClicked.emit(self, event, row, col) 

class ScatterPlot(pg.GraphicsLayoutWidget):
    def __init__(self):
        pg.GraphicsLayoutWidget.__init__(self)
        self.setRenderHints(self.renderHints() | pg.QtGui.QPainter.Antialiasing)

class TracePlot(pg.GraphicsLayoutWidget):
    def __init__(self):
        pg.GraphicsLayoutWidget.__init__(self)
        self.setRenderHints(self.renderHints() | pg.QtGui.QPainter.Antialiasing)

class MatrixAnalyzer(object):
    def __init__(self, cell_classes, title, session):
        self.session = session
        self.cell_classes = cell_classes
        self.session = session
        self.win = MainWindow()
        self.win.show()
        self.win.setWindowTitle(title)

        self.win.filter_control_panel.update_button.clicked.connect(self.update_clicked)
        self.win.matrix_widget.sigClicked.connect(self.display_matrix_element_data)

    def update_clicked(self):
        with pg.BusyCursor():
            self.update_matrix()

    def element_connection_list(self, pre_class, post_class):
        results = ConnectivityAnalyzer(self.pair_groups).measure()
        connections = results[(pre_class, post_class)]['connected_pairs']
        print ("Connection type: %s -> %s" % (pre_class, post_class))
        print ("Connected Pairs:")
        for connection in connections:
            print ("\t %s" % (connection))
        probed_pairs = results[(pre_class, post_class)]['probed_pairs']
        print ("Probed Pairs:")
        for probed in probed_pairs:
            print ("\t %s" % (probed))

    def display_matrix_element_data(self, matrix_widget, event, row, col):
        pre_class, post_class = self.matrix_map[row, col]
        self.element_connection_list(pre_class, post_class)

    def update_matrix(self):
        project_names = self.win.filter_control_panel.selected_project_names()
        matrix_analysis_name = self.win.filter_control_panel.selected_analyzer()

        # Select pairs (todo: age, acsf, internal, temp, etc.)
        self.pairs = query_pairs(project_name=project_names, session=self.session).all()

        # Group all cells by selected classes
        cell_groups = classify_cells(self.cell_classes, pairs=self.pairs)

        # Group pairs into (pre_class, post_class) groups
        self.pair_groups = classify_pairs(self.pairs, cell_groups)

        # analyze matrix elements
        matrix_analysis = self.win.filter_control_panel.analyzers[matrix_analysis_name[0]](self.pair_groups)
        results = matrix_analysis.measure()

        shape = (len(cell_groups),) * 2
        text = np.empty(shape, dtype=object)
        fgcolor = np.empty(shape, dtype=object)
        bgcolor = np.empty(shape, dtype=object)
        bordercolor = np.empty(shape, dtype=object)

        # call display function on every matrix element
        
        self.matrix_map = {}
        for i,row in enumerate(cell_groups):
            for j,col in enumerate(cell_groups):
                output = matrix_analysis.display(row, col, results[(row, col)])
                self.matrix_map[i, j] = (row, col)
                text[i, j] = output['text']
                fgcolor[i, j] = output['fgcolor']
                bgcolor[i, j] = output['bgcolor']
                bordercolor[i, j] = output['bordercolor']
                
        # Force cell class descriptions down to tuples of 2 items
        # Kludgy, but works for now.
        rows = []
        for cell_class in self.cell_classes:
            tup = cell_class.as_tuple
            row = tup[:1]
            if len(tup) > 1:
                row = row + (' '.join(tup[1:]),)
            rows.append(row)

        self.win.matrix_widget.set_matrix_data(text=text, fgcolor=fgcolor, bgcolor=bgcolor, border_color=bordercolor,
                    rows=rows, cols=rows, size=50, header_color='k')
        
        matrix_analysis.summary(results)


if __name__ == '__main__':

    import pyqtgraph as pg
    pg.dbg()

    session = db.Session()
    
    # Define cell classes

    mouse_cell_classes = [
        # {'cre_type': 'unknown', 'pyramidal': True, 'target_layer': '2/3'},
        # {'cre_type': 'unknown', 'target_layer': '2/3'},
        # {'pyramidal': True, 'target_layer': '2/3'},
        {'pyramidal': True, 'target_layer': '2/3'},
        {'cre_type': 'pvalb', 'target_layer': '2/3'},
        {'cre_type': 'sst', 'target_layer': '2/3'},
        {'cre_type': 'vip', 'target_layer': '2/3'},
        {'cre_type': 'rorb', 'target_layer': '4'},
        {'cre_type': 'nr5a1', 'target_layer': '4'},
        {'cre_type': 'pvalb', 'target_layer': '4'},
        {'cre_type': 'sst', 'target_layer': '4'},
        {'cre_type': 'vip', 'target_layer': '4'},
        {'cre_type': 'sim1', 'target_layer': '5'},
        {'cre_type': 'tlx3', 'target_layer': '5'},
        {'cre_type': 'pvalb', 'target_layer': '5'},
        {'cre_type': 'sst', 'target_layer': '5'},
        {'cre_type': 'vip', 'target_layer': '5'},
        {'cre_type': 'ntsr1', 'target_layer': '6'},
        {'cre_type': 'pvalb', 'target_layer': '6'},
        {'cre_type': 'sst', 'target_layer': '6'},
        {'cre_type': 'vip', 'target_layer': '6'},
    ]

    human_cell_classes = [
        {'pyramidal': True, 'target_layer': '2'},
        {'pyramidal': False, 'target_layer': '2'},
        {'pyramidal': True, 'target_layer': '3'},
        {'pyramidal': False, 'target_layer': '3'},
        {'pyramidal': True, 'target_layer': '4'},
        {'pyramidal': False, 'target_layer': '4'},
        {'pyramidal': True, 'target_layer': '5'},
        {'pyramidal': False, 'target_layer': '5'},
        {'pyramidal': True, 'target_layer': '6'},
        {'pyramidal': False, 'target_layer': '6'},
    ]

    analyzers = []
    for cell_classes, title in [(mouse_cell_classes, 'Mouse'), (human_cell_classes, 'Human')]:
        cell_classes = [CellClass(**c) for c in cell_classes]

        maz = MatrixAnalyzer(cell_classes, title=title, session=session)
        analyzers.append(maz)