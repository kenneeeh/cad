class BPTM45nmAreaEstimator:
    def __init__(self, circuit_params, circuit_multipliers):
        self.circuit_params = circuit_params
        self.circuit_multipliers = circuit_multipliers
    
    def find_area(self):
        area = 0
        transistors = {name: (self.circuit_params[name], self.circuit_params['w' + name[1:]], self.circuit_params['l' + name[1:]])
                        for name in self.circuit_params.keys() if 'm' in name}
        # only loop through parameters that 
        for param_name, multiplier in self.circuit_multipliers.items():
            if 'm' in param_name:
                area += self.compute_transistor_area(*transistors[param_name]) * multiplier
            elif 'res' in param_name:
                area += self.compute_resistor_area(self.circuit_params[param_name]) * multiplier
            elif 'cap' in param_name:
                area += self.compute_capacitor_area(self.circuit_params[param_name]) * multiplier
        
        return area
            
    
    def compute_transistor_area(self, m, w, l):
        Wext = 50e-9 # 50 nm
        Lext = 160e-9 # 160 nm

        one_finger_area = w * l + 2 * (w * Lext + Wext * l)
        all_fingers_area = m * one_finger_area

        return all_fingers_area

    def compute_capacitor_area(self, c):
        # (1e-6)**2 --> um^2  ,  1e-15 --> fF
        farad_to_area_ratio = (100 * (1e-6)**2) / (300 * 1e-15)
        cap_area = c * farad_to_area_ratio

        return cap_area

    def compute_resistor_area(self, r):
        ohm_to_area_ratio = (1e-6)**2 / 14
        res_area = r * ohm_to_area_ratio

        return res_area