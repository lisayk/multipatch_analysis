"""
Question: can we digitally remove pipette electrical / capacitive crosstalk somehow?

"""
import numpy as np
import pyqtgraph as pg

from neuroanalysis.data import TraceList
from multipatch_analysis.ui.experiment_browser import ExperimentBrowser
from multipatch_analysis.connection_strength import get_amps, get_baseline_amps
from multipatch_analysis import database as db



class StimResponseList(object):
    """A collection of stimulus-response objects that provides some common analysis tools
    """
    def __init__(self, srs):
        self.srs = srs
        self._plot_items = []
        self._post_tseries = {}
        self._pre_tseries = {}
        
    def clear_plots(self):
        for item in self._plot_items:
            item.scene().removeItem(item)
        self._plot_items = []

    def get_tseries(self, series, bsub=True, align='stim', bsub_window=(-3e-3, 0)):
        """Return a TraceList of timeseries, optionally baseline-subtracted and time-aligned.
        
        Parameters
        ----------
        series : str
            "stim", "pre", or "post"
        """
        assert series in ('stim', 'pre', 'post'), "series must be one of 'stim', 'pre', or 'post'"
        tseries = []
        for i,sr in enumerate(self.srs[:10]):
            ts = getattr(sr, series + '_tseries')
            if bsub:
                bstart = sr.stim_pulse.onset_time + bsub_window[0]
                bstop = sr.stim_pulse.onset_time + bsub_window[1]
                baseline = np.median(ts.time_slice(bstart, bstop).data)
                ts = ts - baseline
            if align is not None:
                if align == 'stim':
                    t_align = sr.stim_pulse.onset_time 
                elif align == 'spike':
                    t_align = sr.stim_pulse.stim_spike.max_dvdt_time
                else:
                    raise ValueError("invalid time alignment mode %r" % align)
                ts = ts.copy(t0=ts.t0-t_align)
            tseries.append(ts)
        return TraceList(tseries)

    def plot_stimulus(self, plt):
        stim_ts = self.get_tseries('stim')
        self._plot_ts(stim_ts, plt)
    
    def plot_presynaptic(self, plt):
        pre_ts = self.get_tseries('pre')
        self._plot_ts(pre_ts, plt)

    def plot_postsynaptic(self, plt):
        post_ts = self.get_tseries('post')
        self._plot_ts(post_ts, plt)
        
    def _plot_ts(self, ts_list, plt):        
        for ts in ts_list:
            item = plt.plot(ts.time_values, ts.data)
            self._plot_items.append(item)
        avg = ts_list.mean()
        item = plt.plot(avg.time_values, avg.data, pen='g', shadowPen={'color':'k', 'width':2})
        self._plot_items.append(item)


class CrosstalkAnalyzer(object):
    """User interface for exploring crosstalk removal methods
    """
    def __init__(self, expt_browser=None):
        if expt_browser is None:
            expt_browser = ExperimentBrowser()
        self.expt_browser = expt_browser
        expt_browser.itemSelectionChanged.connect(self.expt_selection_changed)
        self.session = db.Session()
        
        self.response_list = None
        
        self.pw = pg.GraphicsLayoutWidget()
        
        self.plt1 = self.pw.addPlot(0, 0)
        self.plt2 = self.pw.addPlot(1, 0)
        self.plt3 = self.pw.addPlot(2, 0)
        self.plt2.setXLink(self.plt1)
        self.plt3.setXLink(self.plt1)

    def show(self):
        self.win = pg.QtGui.QSplitter(pg.QtCore.Qt.Horizontal)
        self.win.addWidget(self.expt_browser)
        self.win.addWidget(self.pw)
        self.win.show()
        return self.win
        
    def expt_selection_changed(self):
        sel = self.expt_browser.selectedItems()
        if len(sel) == 0:
            return
        sel = sel[0]
        if not hasattr(sel, 'pair'):
            return
        self.load_pair(sel.pair)

    def load_pair(self, pair):
        with pg.BusyCursor():
            if self.response_list is not None:
                self.response_list.clear_plots()
            
            # preload pulse response data
            db.query(db.PulseResponse.data).filter(db.PulseResponse.pair_id==pair.id).all()
            
            self.response_list = StimResponseList(pair.pulse_responses)
            
            self.response_list.plot_stimulus(self.plt1)
            self.response_list.plot_presynaptic(self.plt2)
            self.response_list.plot_postsynaptic(self.plt3)

        

if __name__ == '__main__':
    import sys
    app = pg.mkQApp()
    pg.dbg()
    
    cta = CrosstalkAnalyzer()
    win = cta.show()
    win.resize(1400, 1000)
    
    if sys.flags.interactive == 0:
        app.exec_()
