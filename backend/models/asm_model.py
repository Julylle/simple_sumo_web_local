import numpy as np
import pandas as pd
# from scipy.integrate import ode
# import time
# import matplotlib.pyplot as plt
# from scipy.integrate import solve_ivp
# from scipy.interpolate import interp1d
from config.paths import DYNAMIC_DATA_FILE


class MonodSingleTank:
    def __init__(self, uAOB=1.96, bAOB=0.07, uNOB=0.79, bNOB=0.05, uH=6.24, bH=0.75, 
                KAOB1O=1, KAOB2O = 0.6, KAOBNH=0.1, KNOBNH = 0.02, KHNH = 0.02, 
                KNOBO=1.1, KNOBNO2=0.51, KAOBNO2=0.14, KHO = 0.1, KHNO2 = 0.2, KHNO3 = 0.2,
                KHS1=20, KHS2=20, KHS3=20, KHS4=20, KHS5 = 40,
                etag2=0.28, etag3=0.16, etag4=0.35, etag5=0.35):
        
        self.uAOB = uAOB/24/60 # min^-1
        self.bAOB = bAOB/24/60 # min^-1
        self.uNOB = uNOB/24/60 # min^-1
        self.bNOB = bNOB/24/60 # min^-1
        self.uH = uH/24/60 # min^-1
        self.bH = bH/24/60 # min^-1
        self.KAOB1O = KAOB1O
        self.KAOB2O = KAOB2O
        self.KAOBNH = KAOBNH
        self.KNOBNH = KNOBNH
        self.KHNH = KHNH
        self.KNOBO = KNOBO
        self.KNOBNO2 = KNOBNO2
        self.KAOBNO2 = KAOBNO2
        self.KHO = KHO
        self.KHS1 = KHS1
        self.KHS2 = KHS2
        self.KHS3 = KHS3
        self.KHS4 = KHS4
        self.KHS5 = KHS5
        self.KHNO2 = KHNO2
        self.KHNO3 = KHNO3
        self.etag2 = etag2
        self.etag3 = etag3
        self.etag4 = etag4
        self.etag5 = etag5

    def __call__(self, state_variables):
        
        self.S_N2 = max(state_variables[0], 0)
        self.S_N2O = max(state_variables[1], 0)
        self.S_NH2OH = max(state_variables[2], 0)
        self.S_NH = max(state_variables[3], 0)
        self.S_NO2 = max(state_variables[4], 0)
        self.S_NO3 = max(state_variables[5], 0)
        self.S_NO = max(state_variables[6], 0)
        self.S_O = max(state_variables[7], 0)
        self.S_S = max(state_variables[8], 0)
        self.X_AOB = max(state_variables[9], 0)
        self.X_H = max(state_variables[10], 0)
        self.X_I = max(state_variables[11], 0)
        self.X_NOB = max(state_variables[12], 0)
        
        fXI = 0.08
        iNSS = 0.03
        iNXB = 0.07
        iNXI = 0.07
        YAOB = 0.15 # 0.24, 0.15
        YAOB1 = 0.75*YAOB
        YAOB2 = 0.25*YAOB
        YNOB = 0.057
        YH = 0.6
        
        ## AOB kinetic parameters
        etaAOBND = 0.25
        etaAOBNN = 0.0015
        KAOBHAONO = 0.0003
        KAOBNH2OH = 0.9
        KAOBIO = 0.8
        KAOBNDO = 0.5
        KAOBNNNO = 0.008
        ## Heterotroph kinetic parameters
        KHI3NO = 0.5
        KHI4NO = 0.3
        KHI5NO = 0.075
        KHN2O = 0.05
        KHNO = 0.05
        etaY = 0.9

        # Ammonia oxidizing bacteria
        rho1 = max(self.uAOB/YAOB*self.S_O/(self.KAOB1O + self.S_O)*self.S_NH/(self.KAOBNH+self.S_NH)*self.X_AOB, 0)    # 1 - Ammonia oxidation
        rho2 = max(self.uAOB*self.S_O/(self.KAOB2O+self.S_O)*self.S_NH2OH/(KAOBNH2OH+self.S_NH2OH)*self.S_NH/(self.KAOBNH+self.S_NH)*self.X_AOB, 0)  # 2 - NO production
        rho3 = max(self.uAOB*self.S_O/(self.KAOB2O+self.S_O)*self.S_NO/(KAOBHAONO+self.S_NO)*self.X_AOB, 0)  # 3 - NO2- production
        FO = self.S_O/(KAOBNDO+(1-2*(KAOBNDO/KAOBIO)**(1/2))*self.S_O+(self.S_O**2/KAOBIO))
        rho4 = max(self.uAOB*etaAOBND/YAOB*self.S_NO2/(self.KAOBNO2+self.S_NO2)*self.S_NH2OH/(KAOBNH2OH+self.S_NH2OH)*FO*self.X_AOB, 0)    # 4 - N2O production (ND pathway)
        rho5 = max(self.uAOB*etaAOBNN/YAOB*self.S_NO/(KAOBNNNO+self.S_NO)*self.S_NH2OH/(KAOBNH2OH+self.S_NH2OH)*self.X_AOB, 0)    # 5 - N2O production (NN pathway)
        rho6 = max(self.bAOB*self.X_AOB, 0)    # 6 - Decay
        # Nitrite oxidizing bacteria
        rho7 = max(self.uNOB*self.S_O/(self.KNOBO+self.S_O)*self.S_NH/(self.KNOBNH+self.S_NH)*self.S_NO2/(self.KNOBNO2+self.S_NO2)*self.X_NOB, 0)    # 7 - Growth
        rho8 = max(self.bNOB*self.X_NOB, 0)  # 8 - Deacy
        # Heterotrophs
        rho9 = max(self.uH*self.S_O/(self.KHO+self.S_O)*self.S_NH/(self.KHNH+self.S_NH)*self.S_S/(self.KHS1+self.S_S)*self.X_H, 0)    # 9 - Aerobic growth
        rho10 = max(self.uH*self.etag2*self.S_S/(self.KHS2+self.S_S)*self.S_NO3/(self.KHNO3+self.S_NO3)*self.KHO/(self.KHO+self.S_O)*self.S_NH/(self.KHNH+self.S_NH)*self.X_H, 0)    # 10 - NO3- reduction
        rho11 = max(self.uH*self.etag3*self.S_S/(self.KHS3+self.S_S)*self.S_NO2/(self.KHNO2+self.S_NO2)*KHI3NO/(KHI3NO+self.S_NO)*self.KHO/(self.KHO+self.S_O)*self.S_NH/(self.KHNH+self.S_NH)*self.X_H, 0)  # 11 - NO2- reductuon
        rho12 = max(self.uH*self.etag4*self.S_S/(self.KHS4+self.S_S)*self.S_NO/(KHNO+self.S_NO+self.S_NO**2/KHI4NO)*self.KHO/(self.KHO+self.S_O)*self.S_NH/(self.KHNH+self.S_NH)*self.X_H, 0)    # 12 - N2O production (HD pathway)
        rho13 = max(self.uH*self.etag5*self.S_S/(self.KHS5+self.S_S)*self.S_N2O/(KHN2O+self.S_N2O)*self.KHO/(self.KHO+self.S_O)*KHI5NO/(KHI5NO+self.S_NO)*self.S_NH/(self.KHNH+self.S_NH)*self.X_H, 0)  # 13 - N2O consumption (HD pathway)
        rho14 = max(self.bH*self.X_H, 0)    # 14 - Deacy
        
        r1 = -rho1 -iNXB*(rho2 + rho3 + rho7) + (iNXB-fXI*iNXI-(1-fXI)*iNSS)*(rho6 + rho8 + rho14) + (iNSS/YH-iNXB)*rho9 + (iNSS/YH/etaY-iNXB)*(rho10 + rho11 + rho12 + rho13)   # SNH  
        r2 = rho1 - rho2/YAOB1 - rho4 - rho5   # SNH2OH
        r3 = (1-YH*etaY)/(0.57*YH*etaY)*rho13    # SN2
        r4 = 2*rho4 + 4*rho5 + (1-YH*etaY)/(0.57*YH*etaY)*(rho12 - rho13)   # SN2O
        r5 = rho2/YAOB1 - rho3/YAOB2 - 4*rho5 + (1-YH*etaY)/(0.57*YH*etaY)*(rho11 - rho12)   # SNO
        r6 = rho3/YAOB2 - rho4 + rho5 - rho7/YNOB + (1-YH*etaY)/(1.14*YH*etaY)*rho10 - (1-YH*etaY)/(0.57*YH*etaY)*rho11   # SNO2
        r7 = rho7/YNOB - (1-YH*etaY)/(1.14*YH*etaY)*rho10   # SNO3
        r8 = -1.14*rho1 + (1-1.71/YAOB1)*rho2 + (1-0.57/YAOB2)*rho3 + (1-1.14/YNOB)*rho7 + (1-1/YH)*rho9   # SO
        r9 = (1-fXI)*(rho6 + rho8 + rho14) - rho9/YH - (rho10 + rho11 + rho12 + rho13)/(YH*etaY) # SS
        r10 = rho2 + rho3 - rho6    # XAOB
        r11 = rho7 - rho8   # XNOB
        r12 = rho9 + rho10 + rho11 + rho12 + rho13 -rho14   # XH
        r13 = fXI*(rho6 + rho8 + rho14)     # XI
        
        return [r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12, r13]


class GrowthCoupledProduction:
    def __init__(self, model_parameters):
        super(GrowthCoupledProduction, self).__init__()
        self.model_parameters = model_parameters
        self.dynamicSwitch = self.model_parameters['dynamicSwitch']
        self.SingleTank = MonodSingleTank(**{k: v for k, v in model_parameters.items() if k in MonodSingleTank.__init__.__code__.co_varnames})
        # Dictionary Comprehension distract parameters from model_parameters for MonodSingleTank contractor function

        if model_parameters['dynamicSwitch']:

            self.dyInput = pd.read_excel(DYNAMIC_DATA_FILE, sheet_name='dyinput', header=0)
            # rawInlet.set_index('Time', inplace=True)
            # self.dyInput = rawInlet.resample('H').mean()
            # self.do_interpolators = {
            #     f'S{i}O': interp1d(self.dyInput.index * 60, self.dyInput[f'S{i}O'], kind='linear', fill_value='extrapolate')
            #     for i in range(1, 9)
            # }

        self.Vaerobic = 467454.51      # L
        self.Vanoxic = 233727.29       # L
        self.SOsat = model_parameters['SOsat']
        self.Rdiff = 0.9640
        self.SN2Oequi = 1.695E-04  # mg/L



    def get_dynamic_inputs(self, t):
        if self.model_parameters['dynamicSwitch']:
            # Use the most recent input row.  ``iloc`` avoids treating the
            # integer as an index label, and clipping keeps the final solver
            # evaluation within the available input data.
            mag_kla1O2 = self.model_parameters['kla1O2']
            mag_kla2O2 = self.model_parameters['kla2O2']
            mag_kla3O2 = self.model_parameters['kla3O2']
            tot_Af = self.dyInput["Aeration Tank 4_m3/h"]/60/60 # m3/s
            Ae1_per =  0.55
            Ae2_per =  0.26
            Ae3_per =  0.19
            Aerobic_area = 141.6528818
            Ae1_Vg = tot_Af * Ae1_per / Aerobic_area
            Ae2_Vg = tot_Af * Ae2_per / Aerobic_area
            Ae3_Vg = tot_Af * Ae3_per / Aerobic_area
            d_R = 3.3 # m
            d_L = 0.815 # lab reactor depth
            # tempcorr = pow(1.024,temp-20)
            kla1O2_cal = pow(d_R/d_L,-0.49)*34500*pow(Ae1_Vg,0.86)/self.model_parameters['Rdiff'] # day^-1
            kla2O2_cal = pow(d_R/d_L,-0.49)*34500*pow(Ae2_Vg,0.86)/self.model_parameters['Rdiff'] # day^-1
            kla3O2_cal = pow(d_R/d_L,-0.49)*34500*pow(Ae3_Vg,0.86)/self.model_parameters['Rdiff'] # day^-1
            mag_corr1 = mag_kla1O2/kla1O2_cal[:8].mean()
            mag_corr2 = mag_kla2O2/kla2O2_cal[:8].mean()
            mag_corr3 = mag_kla3O2/kla3O2_cal[:8].mean()
            kla1O2_dyna = kla1O2_cal*mag_corr1
            kla2O2_dyna = kla2O2_cal*mag_corr2
            kla3O2_dyna = kla3O2_cal*mag_corr3
            t_index = min(max(int(t / 60), 0), len(self.dyInput) - 1)
            row = self.dyInput.iloc[t_index]
            influent = (row["Effluent rate (L/s)"] + row["WAS (L/s)"]) * 60 / 11 # L/min, convert to single lane
            MLR = influent * self.model_parameters['qmlr_ratio'] # L/min
            # Dynamic KLa columns are optional.  The configured values are in
            # day^-1, so convert them to min^-1 when the worksheet omits them.
            if self.model_parameters['constantKLa']:
                kla1O2 = self.model_parameters['kla1O2'] / 24 / 60
                kla2O2 = self.model_parameters['kla2O2'] / 24 / 60
                kla3O2 = self.model_parameters['kla3O2'] / 24 / 60
            else:
                kla1O2 = kla1O2_dyna[t_index] / 24 / 60 # min-1
                kla2O2 = kla2O2_dyna[t_index] / 24 / 60 # min-1
                kla3O2 = kla3O2_dyna[t_index] / 24 / 60 # min-1

            return (
                row.SNH,
                0, # self.dyInput.SNH2OH[t_index],
                0, # self.dyInput.SN2[t_index],
                0, # self.dyInput.SN2O[t_index],
                0, # self.dyInput.SNO[t_index],
                row.SNO2,
                row.SNO3,
                0, # self.dyInput.SO[t_index],
                row.bCOD,
                0, # self.dyInput.XAOB[t_index],
                0, # self.dyInput.XNOB[t_index],
                0, # self.dyInput.XH[t_index],
                row.XI, # XI
                influent,
                MLR,
                row["RAS (L/s)"] * 60 / 11, # L/min, convert to single lane
                row["WAS (L/s)"] * 60 / 11, # L/min, convert to single lane
                kla1O2, # min-1
                kla2O2, # min-1,
                kla3O2, # min-1,
                )

        else:
            MLR = self.model_parameters['qinlet'] * self.model_parameters['qmlr_ratio'] * 60
            return (
                self.model_parameters['SNHinlet'],
                self.model_parameters['SNH2OHinlet'],
                self.model_parameters['SN2inlet'],
                self.model_parameters['SN2Oinlet'],
                self.model_parameters['SNOinlet'],
                self.model_parameters['SNO2inlet'],
                self.model_parameters['SNO3inlet'],
                self.model_parameters['SOinlet'],
                self.model_parameters['SSinlet'],
                self.model_parameters['XAOBinlet'],
                self.model_parameters['XNOBinlet'],
                self.model_parameters['XHinlet'],
                self.model_parameters['XIinlet'],
                self.model_parameters['qinlet'] * 60, # L/min
                MLR, # L/min
                self.model_parameters['qras'] * 60, # L/min
                self.model_parameters['qwas'] * 60, # L/min
                self.model_parameters['kla1O2']/24/60, # min-1
                self.model_parameters['kla2O2']/24/60, # min-1
                self.model_parameters['kla3O2']/24/60, # min-1
            )

    def rhs(self, t, y):
        S1N2, S1N2O, S1NH, S1NH2OH, S1NO, S1NO2, S1NO3, S1O, S1S, \
        S2N2, S2N2O, S2NH, S2NH2OH, S2NO, S2NO2, S2NO3, S2O, S2S, \
        S3N2, S3N2O, S3NH, S3NH2OH, S3NO, S3NO2, S3NO3, S3O, S3S, \
        S4N2, S4N2O, S4NH, S4NH2OH, S4NO, S4NO2, S4NO3, S4O, S4S, \
        S5N2, S5N2O, S5NH, S5NH2OH, S5NO, S5NO2, S5NO3, S5O, S5S, \
        X1AOB, X1H, X1I, X1NOB, X2AOB, X2H, X2I, X2NOB, \
        X3AOB, X3H, X3I, X3NOB, X4AOB, X4H, X4I, X4NOB, \
        X5AOB, X5H, X5I, X5NOB = y


        # if self.model_parameters['dynamicSwitch']:
        (SNHinlet, SNH2OHinlet, SN2inlet, SN2Oinlet, SNOinlet, SNO2inlet, SNO3inlet,
            SOinlet, SSinlet, XAOBinlet, XNOBinlet, XHinlet, XIinlet,
            qinlet, qmlr, qras, qwas, kla1O2, kla2O2, kla3O2,
            ) = self.get_dynamic_inputs(t)
        self.qwas = qwas
        sludgeR = (qinlet + qras) / (self.qwas + qras)

        r11, r12, r13, r14, r15, r16, r17, r18, r19, r110, r111, r112, r113 = self.SingleTank(
            [S1N2, S1N2O, S1NH2OH, S1NH, S1NO2, S1NO3, S1NO, S1O, S1S, X1AOB, X1H, X1I, X1NOB])

        r21, r22, r23, r24, r25, r26, r27, r28, r29, r210, r211, r212, r213 = self.SingleTank(
            [S2N2, S2N2O, S2NH2OH, S2NH, S2NO2, S2NO3, S2NO, S2O, S2S, X2AOB, X2H, X2I, X2NOB])

        r31, r32, r33, r34, r35, r36, r37, r38, r39, r310, r311, r312, r313 = self.SingleTank(
            [S3N2, S3N2O, S3NH2OH, S3NH, S3NO2, S3NO3, S3NO, S3O, S3S, X3AOB, X3H, X3I, X3NOB])

        r41, r42, r43, r44, r45, r46, r47, r48, r49, r410, r411, r412, r413 = self.SingleTank(
            [S4N2, S4N2O, S4NH2OH, S4NH, S4NO2, S4NO3, S4NO, S4O, S4S, X4AOB, X4H, X4I, X4NOB])

        r51, r52, r53, r54, r55, r56, r57, r58, r59, r510, r511, r512, r513 = self.SingleTank(
            [S5N2, S5N2O, S5NH2OH, S5NH, S5NO2, S5NO3, S5NO, S5O, S5S, X5AOB, X5H, X5I, X5NOB])


        Dinlet = qinlet / self.Vanoxic  # min^-1
        Dras = qras / self.Vanoxic  # min^-1
        Dmlr = qmlr / self.Vanoxic  # min^-1

        # Anoxic tank 1 (An1), 1 
        dS1NHdt = Dinlet * (SNHinlet - S1NH) + (Dras + Dmlr) * (S5NH - S1NH) + r11
        dS1NH2OHdt = Dinlet * (SNH2OHinlet - S1NH2OH) + (Dras + Dmlr) * (S5NH2OH - S1NH2OH) + r12
        dS1N2dt = Dinlet * (SN2inlet - S1N2) + (Dras + Dmlr) * (S5N2 - S1N2) + r13
        dS1N2Odt = Dinlet * (SN2Oinlet - S1N2O) + (Dras + Dmlr) * (S5N2O - S1N2O) + r14
        dS1NOdt = Dinlet * (SNOinlet - S1NO) + (Dras + Dmlr) * (S5NO - S1NO) + r15
        dS1NO2dt = Dinlet * (SNO2inlet - S1NO2) + (Dras + Dmlr) * (S5NO2 - S1NO2) + r16
        dS1NO3dt = Dinlet * (SNO3inlet - S1NO3) + (Dras + Dmlr) * (S5NO3 - S1NO3) + r17
        if self.model_parameters['DOSetpoint']:
            dS1Odt = 0
        else:
            dS1Odt = Dinlet * (SOinlet - S1O) + (Dras + Dmlr) * (S5O - S1O) + r18
        dS1Sdt = Dinlet * (SSinlet - S1S) + (Dras + Dmlr) * (S5S - S1S) + r19
        dX1AOBdt = Dinlet * (XAOBinlet - X1AOB) + Dmlr * (X5AOB - X1AOB) + Dras * (X5AOB * sludgeR - X1AOB) + r110
        dX1NOBdt = Dinlet * (XNOBinlet - X1NOB) + Dmlr * (X5NOB - X1NOB) + Dras * (X5NOB * sludgeR - X1NOB) + r111
        dX1Hdt = Dinlet * (XHinlet - X1H) + Dmlr * (X5H - X1H) + Dras * (X5H * sludgeR - X1H) + r112
        dX1Idt = Dinlet * (XIinlet - X1I) + Dmlr * (X5I - X1I) + Dras * (X5I * sludgeR - X1I) + r113

        # Anoxic tank 2 (An2), 2
        Dadd2 = (qinlet + qras + qmlr) / self.Vanoxic  # min^-1

        dS2NHdt = Dadd2 * (S1NH - S2NH) + r21
        dS2NH2OHdt = Dadd2 * (S1NH2OH - S2NH2OH) + r22
        dS2N2dt = Dadd2 * (S1N2 - S2N2) + r23
        dS2N2Odt = Dadd2 * (S1N2O - S2N2O) + r24
        dS2NOdt = Dadd2 * (S1NO - S2NO) + r25
        dS2NO2dt = Dadd2 * (S1NO2 - S2NO2) + r26
        dS2NO3dt = Dadd2 * (S1NO3 - S2NO3) + r27
        if self.model_parameters['DOSetpoint']:
            dS2Odt = 0
        else:
            dS2Odt =  Dadd2 * (S1O - S2O) + r28
        dS2Sdt = Dadd2 * (S1S - S2S) + r29
        dX2AOBdt = Dadd2 * (X1AOB - X2AOB) + r210
        dX2NOBdt = Dadd2 * (X1NOB - X2NOB) + r211
        dX2Hdt = Dadd2 * (X1H - X2H) + r212
        dX2Idt = Dadd2 * (X1I - X2I) + r213

        # Aerobic tank 1, 3
        Dadd3 = (qinlet + qras + qmlr) / self.Vaerobic  # min^-1

        dS3NHdt = Dadd3 * (S2NH - S3NH) + r31
        dS3NH2OHdt = Dadd3 * (S2NH2OH - S3NH2OH) + r32
        dS3N2dt = Dadd3 * (S2N2 - S3N2) + r33
        dS3N2Odt = Dadd3 * (S2N2O - S3N2O) + r34# - kla2O2 * self.Rdiff * (S3N2O - self.SN2Oequi)
        # dS3N2OGdt = kla2O2 * self.Rdiff * (S3N2O - self.SN2Oequi)*self.Vaerobic/1000 # gN/min
        dS3NOdt = Dadd3 * (S2NO - S3NO) + r35
        dS3NO2dt = Dadd3 * (S2NO2 - S3NO2) + r36
        dS3NO3dt = Dadd3 * (S2NO3 - S3NO3) + r37
        if self.model_parameters['DOSetpoint']:
            dS3Odt = 0
        else:
            dS3Odt = Dadd3 * (S2O - S3O) + r38 + kla1O2 * (self.SOsat - S3O)
        dS3Sdt = Dadd3 * (S2S - S3S) + r39
        dX3AOBdt = Dadd3 * (X2AOB - X3AOB) + r310
        dX3NOBdt = Dadd3 * (X2NOB - X3NOB) + r311
        dX3Hdt = Dadd3 * (X2H - X3H) + r312
        dX3Idt = Dadd3 * (X2I - X3I) + r313

        # Aerobic tank 2 (Ae2), 4
        Dadd4 = (qinlet + qmlr + qras) / self.Vaerobic  # min^-1

        dS4NHdt = Dadd4 * (S3NH - S4NH) + r41
        dS4NH2OHdt = Dadd4 * (S3NH2OH - S4NH2OH) + r42
        dS4N2dt = Dadd4 * (S3N2 - S4N2) + r43
        dS4N2Odt = Dadd4 * (S3N2O - S4N2O) + r44#- kla2O2 * self.Rdiff * (S4N2O - self.SN2Oequi)
        # dS4N2OGdt = kla2O2 * self.Rdiff * (S4N2O - self.SN2Oequi)*self.Vaerobic/1000 # gN/min
        dS4NOdt = Dadd4 * (S3NO - S4NO) + r45
        dS4NO2dt = Dadd4 * (S3NO2 - S4NO2) + r46
        dS4NO3dt = Dadd4 * (S3NO3 - S4NO3) + r47
        if self.model_parameters['DOSetpoint']:
            dS4Odt = 0
        else:
            dS4Odt = Dadd4 * (S3O - S4O) + r48 + kla2O2 * (self.SOsat - S4O)
        dS4Sdt = Dadd4 * (S3S - S4S) + r49
        dX4AOBdt = Dadd4 * (X3AOB - X4AOB) + r410
        dX4NOBdt = Dadd4 * (X3NOB - X4NOB) + r411
        dX4Hdt = Dadd4 * (X3H - X4H) + r412
        dX4Idt = Dadd4 * (X3I - X4I) + r413

        # Aerobic tank 3 (Ae3), 5
        Dadd5 = (qinlet + qmlr + qras) / self.Vaerobic  # min^-1

        dS5NHdt = Dadd5 * (S4NH - S5NH) + r51
        dS5NH2OHdt = Dadd5 * (S4NH2OH - S5NH2OH) + r52
        dS5N2dt = Dadd5 * (S4N2 - S5N2) + r53
        dS5N2Odt = Dadd5 * (S4N2O - S5N2O) + r54 #- kla3O2 * self.Rdiff * (S5N2O - self.SN2Oequi)
        # dS5N2OGdt = kla3O2 * self.Rdiff * (S5N2O - self.SN2Oequi)*self.Vaerobic/1000 # gN/min
        dS5NOdt = Dadd5 * (S4NO - S5NO) + r55
        dS5NO2dt = Dadd5 * (S4NO2 - S5NO2) + r56
        dS5NO3dt = Dadd5 * (S4NO3 - S5NO3) + r57
        if self.model_parameters['DOSetpoint']:
            dS5Odt = 0
        else:
            dS5Odt =  Dadd5 * (S4O - S5O) + r58 + kla3O2 * (self.SOsat - S5O)
        dS5Sdt = Dadd5 * (S4S - S5S) + r59
        dX5AOBdt = Dadd5 * (X4AOB - X5AOB) + r510
        dX5NOBdt = Dadd5 * (X4NOB - X5NOB) + r511
        dX5Hdt = Dadd5 * (X4H - X5H) + r512
        dX5Idt = Dadd5 * (X4I - X5I) + r513

        return np.array([
            dS1N2dt, dS1N2Odt, dS1NHdt, dS1NH2OHdt, dS1NOdt, dS1NO2dt, dS1NO3dt, dS1Odt, dS1Sdt,
            dS2N2dt, dS2N2Odt, dS2NHdt, dS2NH2OHdt, dS2NOdt, dS2NO2dt, dS2NO3dt, dS2Odt, dS2Sdt,
            dS3N2dt, dS3N2Odt, dS3NHdt, dS3NH2OHdt, dS3NOdt, dS3NO2dt, dS3NO3dt, dS3Odt, dS3Sdt,
            dS4N2dt, dS4N2Odt, dS4NHdt, dS4NH2OHdt, dS4NOdt, dS4NO2dt, dS4NO3dt, dS4Odt, dS4Sdt,
            dS5N2dt, dS5N2Odt, dS5NHdt, dS5NH2OHdt, dS5NOdt, dS5NO2dt, dS5NO3dt, dS5Odt, dS5Sdt,
            dX1AOBdt, dX1Hdt, dX1Idt, dX1NOBdt, dX2AOBdt, dX2Hdt, dX2Idt, dX2NOBdt,
            dX3AOBdt, dX3Hdt, dX3Idt, dX3NOBdt, dX4AOBdt, dX4Hdt, dX4Idt, dX4NOBdt,
            dX5AOBdt, dX5Hdt, dX5Idt, dX5NOBdt,
                         ])
