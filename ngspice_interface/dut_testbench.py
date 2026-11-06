import time
import numpy as np
import os
import scipy.interpolate as interp
import scipy.optimize as sciopt
from .area_estimation import BPTM45nmAreaEstimator
from .ngspice_wrapper import NgspiceWrapper


class DUT(NgspiceWrapper):
    def measure_metrics(self):
        self.parse_outputs()
        spec_dict = {}
        # post process raw data
        area_estimator = BPTM45nmAreaEstimator(self.circuit_params, self.circuit_multipliers)
        spec_dict['area'] = area_estimator.find_area()
        spec_dict['current'] = self.current
        spec_dict['gain'] = self.find_dc_gain(self.vout_complex)
        spec_dict['noise'] = self.noise
        spec_dict['phm'] = self.find_phm(self.freq, self.vout_complex)
        spec_dict['slewRate'] = self.find_slew_rate(self.time, self.vout_tran, threshold_low=0.1, threshold_high=0.9, time_unit='us')
        spec_dict['ugbw'] = self.find_ugbw(self.freq, self.vout_complex)

        return spec_dict
    
    def parse_outputs(self):
        tran_fname = os.path.join(self.output_files_folder, 'tran_'+self.random_name+'.csv')
        ac_fname = os.path.join(self.output_files_folder, 'ac_'+self.random_name+'.csv')
        dc_fname = os.path.join(self.output_files_folder, 'dc_'+self.random_name+'.csv')
        noise_fname = os.path.join(self.output_files_folder, 'noise_'+self.random_name+'.csv')
        # add these file names in a list
        self.output_files = [tran_fname, ac_fname, dc_fname, noise_fname]
        for file in self.output_files:
            if not os.path.isfile(file):
                print(f"{file} doesn't exist")
        tran_raw_outputs = np.genfromtxt(tran_fname, skip_header=1)
        ac_raw_outputs = np.genfromtxt(ac_fname, skip_header=1)
        dc_raw_outputs = np.genfromtxt(dc_fname, skip_header=1)
        noise_raw_outputs = np.genfromtxt(noise_fname, skip_header=1)

        # wrdata prints ~8 significant digits, so tiny simulator steps can show up as
        # duplicate x values; the splines need strictly increasing x, so keep only unique ones
        self.time, idx = np.unique(tran_raw_outputs[:, 0], return_index=True)
        self.vout_tran = tran_raw_outputs[idx, 1]

        self.freq, idx = np.unique(ac_raw_outputs[:, 0], return_index=True)
        vout_real = ac_raw_outputs[idx, 1]
        vout_imag = ac_raw_outputs[idx, 2]
        self.vout_complex = vout_real + 1j*vout_imag
        
        self.current = - dc_raw_outputs[1]

        self.noise = noise_raw_outputs[0]
    
    def find_dc_gain(self, vout):
        mags = np.abs(vout)
        return mags[0]
        
    def find_ugbw(self, freq, vout):
        res = self._get_best_crossing(freq, np.abs(vout), 1)
        if not res[1]:
            return 0
        else: return res[0]
    
    def find_phm(self, freq, vout):
        gain = np.abs(vout)
        phase = np.unwrap(np.angle(vout)) * 180 / np.pi    # degrees, no +-180 jumps
        ugbw, found = self._get_best_crossing(freq, gain, 1)  # frequency where |A| = 1
        if not found:
            return 0
        phase_fun = interp.InterpolatedUnivariateSpline(freq, phase)
        return 180 + float(phase_fun(ugbw))
    
    def find_slew_rate(self, time, signal, threshold_low=0.1, threshold_high=0.9, time_unit='us'):
        vmin, vmax = np.min(signal), np.max(signal)
        vth_low = vmin + threshold_low * (vmax - vmin)
        vth_high = vmin + threshold_high * (vmax - vmin)

        t_low = interp.InterpolatedUnivariateSpline(time, signal - vth_low).roots()
        t_high = interp.InterpolatedUnivariateSpline(time, signal - vth_high).roots()

        n = min(len(t_low), len(t_high))
        dt = t_high[:n] - t_low[:n]
        dt = dt[dt > 0]  # rising edges only: low threshold is crossed before the high one
        if len(dt) == 0:
            return 0.0
        return np.mean((vth_high - vth_low) / dt) * 1e-6

    def _get_best_crossing(cls, xvec, yvec, val):
        interp_fun = interp.InterpolatedUnivariateSpline(xvec, yvec)

        def fzero(x):
            return interp_fun(x) - val

        xstart, xstop = xvec[0], xvec[-1]
        try:
            return sciopt.brentq(fzero, xstart, xstop), True
        except ValueError:
            return xstop, False
