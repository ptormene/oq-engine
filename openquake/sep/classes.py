# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (C) 2020-2023, GEM Foundation
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.
import abc
import inspect
from openquake.hazardlib import imt
from openquake.sep.landslide.common import static_factor_of_safety, rock_slope_static_factor_of_safety
from openquake.sep.landslide.newmark import (
    newmark_critical_accel,
    newmark_displ_from_pga_M,
    prob_failure_given_displacement,
)
from openquake.sep.landslide.rockfalls import (
    critical_accel_rock_slope,
    newmark_displ_from_pga
)
from openquake.sep.liquefaction.liquefaction import (
    hazus_liquefaction_probability,
    zhu_etal_2015_general,
    zhu_etal_2017_coastal,
    zhu_etal_2017_general,
    rashidian_baise_2020,
    allstadt_etal_2022,
    akhlagi_etal_2021_model_a,
    akhlagi_etal_2021_model_b,
    bozzoni_etal_2021_europe,
    todorovic_silva_2022_nonparametric_general,
    HAZUS_LIQUEFACTION_PGA_THRESHOLD_TABLE,
)
from openquake.sep.liquefaction.lateral_spreading import (
    hazus_lateral_spreading_displacement,
    lateral_spreading_nonparametric_general
)

from openquake.sep.liquefaction.vertical_settlement import (
    hazus_vertical_settlement,
    HAZUS_VERT_SETTLEMENT_TABLE
)

class SecondaryPeril(metaclass=abc.ABCMeta):
    """
    Abstract base class. Subclasses of SecondaryPeril have:

    1. a ``__init__`` method with global parameters coming from the job.ini
    2. a ``prepare(sitecol)`` method modifying on the site collection, called
    in the ``pre_execute`` phase, i.e. before running the calculation
    3. a ``compute(mag, imt, gmf, sites)`` method called during the calculation
    of the GMFs; gmf is an array of length N1 and sites is a (filtered)
    site collection of length N1 (normally N1 < N, the total number of sites)
    4. an ``outputs`` attribute which is a list of column names which will be
    added to the gmf_data array generated by the ground motion calculator

    The ``compute`` method will return a tuple with ``O`` arrays where ``O``
    is the number of outputs.
    """
    outputs = []

    @classmethod
    def __init_subclass__(cls):
        # make sure the name of the outputs are valid IMTs
        for out in cls.outputs:
            imt.from_string(out)

    @classmethod
    def instantiate(cls, secondary_perils, sec_peril_params):
        inst = []
        for clsname in secondary_perils:
            c = globals()[clsname]
            kw = {}
            for param in inspect.signature(c).parameters:
                if param in sec_peril_params:
                    kw[param] = sec_peril_params[param]
            inst.append(c(**kw))
        return inst

    @abc.abstractmethod
    def prepare(self, sites):
        """Add attributes to sites"""

    @abc.abstractmethod
    def compute(self, mag, imt_gmf, sites):
        """
        :param mag: magnitude
        :param imt_gmf: a list of pairs (imt, gmf)
        :param sites: a filtered site collection
        """

    def __repr__(self):
        return '<%s>' % self.__class__.__name__


class NewmarkDisplacement(SecondaryPeril):
    outputs = ["Disp", "DispProb"]

    def __init__(self, c1=-2.71, c2=2.335, c3=-1.478, c4=0.424,
                 crit_accel_threshold=0.05):
        self.c1 = c1
        self.c2 = c2
        self.c3 = c3
        self.c4 = c4
        self.crit_accel_threshold = crit_accel_threshold

    def prepare(self, sites):
        sites.add_col('Fs', float, static_factor_of_safety(
            slope=sites.slope,
            cohesion=sites.cohesion_mid,
            friction_angle=sites.friction_mid,
            saturation_coeff=sites.saturation,
            soil_dry_density=sites.dry_density))
        sites.add_col('crit_accel', float,
                      newmark_critical_accel(sites.Fs, sites.slope))

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGA':
                nd = newmark_displ_from_pga_M(
                    gmf, sites.crit_accel, mag,
                    self.c1, self.c2, self.c3, self.c4,
                    self.crit_accel_threshold)
            out.append(nd)
            out.append(prob_failure_given_displacement(nd))
        return out
    

class GrantEtAl2016RockSlopeFailure(SecondaryPeril):
    outputs = ["Disp"]

    def __init__(self, c1=0.215, c2=2.341, c3=-1.438,
                 crit_accel_threshold=0.05):
        self.c1 = c1
        self.c2 = c2
        self.c3 = c3
        self.crit_accel_threshold = crit_accel_threshold

    def prepare(self, sites):
        sites.add_col('Fs', float, rock_slope_static_factor_of_safety(
            slope=sites.slope,
            cohesion=sites.cohesion_mid,
            friction_angle=sites.friction_mid,
            saturation_coeff=sites.saturation,
            soil_dry_density=sites.dry_density))
        sites.add_col('crit_accel', float,
                      critical_accel_rock_slope(sites.Fs, sites.slope))

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGA':
                nd = newmark_displ_from_pga(
                    gmf, sites.crit_accel, mag,
                    self.c1, self.c2, self.c3,
                    self.crit_accel_threshold)
            out.append(nd)
        return out


class HazusLiquefaction(SecondaryPeril):
    outputs = ["LiqProb"]

    def __init__(self, map_proportion_flag=True):
        self.map_proportion_flag = map_proportion_flag

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGA':
                out.append(hazus_liquefaction_probability(
                    pga=gmf, mag=mag, liq_susc_cat=sites.liq_susc_cat,
                    groundwater_depth=sites.gwd,
                    do_map_proportion_correction=self.map_proportion_flag))
        return out


class HazusDeformation(SecondaryPeril):
    """
    Computes PGDMax or PGDGeomMean from PGA
    """
    def __init__(self, return_unit='m', deformation_component='PGDMax',
        pga_threshold_table=HAZUS_LIQUEFACTION_PGA_THRESHOLD_TABLE,
        settlement_table=HAZUS_VERT_SETTLEMENT_TABLE):
        self.return_unit = return_unit
        self.deformation_component = getattr(imt, deformation_component)
        self.outputs = [deformation_component]

        if pga_threshold_table != HAZUS_LIQUEFACTION_PGA_THRESHOLD_TABLE:
            pga_threshold_table = {bytes(str(k), 'utf-8'): v
                for k, v in pga_threshold_table.items()}
        self.pga_threshold_table=pga_threshold_table

        if settlement_table != HAZUS_VERT_SETTLEMENT_TABLE:
            settlement_table = {bytes(str(k), 'utf-8'): v
                for k, v in settlement_table.items()}
        self.settlement_table=settlement_table

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGA':
                ls = hazus_lateral_spreading_displacement(
                    mag=mag, pga=gmf, liq_susc_cat=sites.liq_susc_cat,
                    pga_threshold_table=self.pga_threshold_table,
                    return_unit=self.return_unit)
                vs = hazus_vertical_settlement(mag=mag,pga=gmf, 
                    liq_susc_cat = sites.liq_susc_cat, 
                    settlement_table=self.settlement_table,
                    return_unit=self.return_unit)
                out.append(self.deformation_component(ls, vs))
        return out


class Rathje2023LateralSpreadNonparametric(SecondaryPeril):
    """
    Computes the lateral spreading class from PGA.
    """
    experimental = True
    outputs = ["LSDClass"]

    def __init__(self):
        pass

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGA':
                out_class = lateral_spreading_nonparametric_general(
                    pga=gmf, elevation=sites.vs30, slope=sites.slope, wtd=sites.gwd, dr=sites.dr)
            out.append(out_class)
        return out


class ZhuEtAl2015LiquefactionGeneral(SecondaryPeril):
    """
    Computes the liquefaction probability from PGA and transforms it
    to binary output via the predefined probability threshold.
    """
    outputs = ["LiqProb","LiqOccur"]

    def __init__(self, intercept=24.1, pgam_coeff=2.067, cti_coeff=0.355, vs30_coeff=-4.784):
        self.intercept = intercept
        self.pgam_coeff = pgam_coeff
        self.cti_coeff = cti_coeff
        self.vs30_coeff = vs30_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGA':
                prob_liq, out_class = zhu_etal_2015_general(
                    pga=gmf, mag=mag, cti=sites.cti, vs30=sites.vs30)
            out.append(prob_liq)
            out.append(out_class)
        return out
    

class ZhuEtAl2017LiquefactionCoastal(SecondaryPeril):
    """
    Computes the liquefaction probability from PGV and transforms it
    to binary output via the predefined probability threshold.
    """
    outputs = ["LiqProb","LiqOccur","LSE"]

    def __init__(self, intercept=12.435, pgv_coeff=0.301, vs30_coeff=-2.615, 
                 dr_coeff=0.0666, dc_coeff=-0.0287, dcdr_coeff = -0.0369, 
                 precip_coeff=0.0005556):
        self.intercept = intercept
        self.pgv_coeff = pgv_coeff
        self.vs30_coeff = vs30_coeff
        self.dr_coeff = dr_coeff
        self.dc_coeff = dc_coeff
        self.dcdr_coeff = dcdr_coeff
        self.precip_coeff = precip_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGV':
                prob_liq, out_class, lse = zhu_etal_2017_coastal(
                    pgv=gmf, vs30=sites.vs30, dr=sites.dr, 
                    dc=sites.dc, precip=sites.precip)
            out.append(prob_liq)
            out.append(out_class)
            out.append(lse)
        return out


class ZhuEtAl2017LiquefactionGeneral(SecondaryPeril):
    """
    Computes the liquefaction probability from PGV and transforms it
    to binary output via the predefined probability threshold.
    """
    outputs = ["LiqProb","LiqOccur","LSE"]

    def __init__(self, intercept=8.801, pgv_scaling_factor=1.0, pgv_coeff=0.334, vs30_coeff=-1.918, 
                 dw_coeff=-0.2054, wtd_coeff=-0.0333, precip_coeff=0.0005408):
        self.intercept = intercept
        self.pgv_scaling_factor = pgv_scaling_factor
        self.pgv_coeff = pgv_coeff
        self.vs30_coeff = vs30_coeff
        self.dw_coeff = dw_coeff
        self.wtd_coeff = wtd_coeff
        self.precip_coeff = precip_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGV':
                prob_liq, out_class, lse = zhu_etal_2017_general(
                    pgv=gmf, vs30=sites.vs30, dw=sites.dw, 
                    wtd=sites.gwd, precip=sites.precip)
            out.append(prob_liq)
            out.append(out_class)
            out.append(lse)
        return out


class RashidianBaise2020Liquefaction(SecondaryPeril):
    """
    Computes the liquefaction probability from PGV and PGA and transforms it
    to binary output via the predefined probability threshold.
    """
    outputs = ["LiqProb","LiqOccur","LSE"]

    def __init__(self, intercept=8.801, pgv_scaling_factor=1.0, pgv_coeff=0.334, vs30_coeff=-1.918, 
                 dw_coeff=-0.2054, wtd_coeff=-0.0333, precip_coeff=0.0005408):
        self.intercept = intercept
        self.pgv_scaling_factor = pgv_scaling_factor
        self.pgv_coeff = pgv_coeff
        self.vs30_coeff = vs30_coeff
        self.dw_coeff = dw_coeff
        self.wtd_coeff = wtd_coeff
        self.precip_coeff = precip_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        pga = None
        pgv = None
        for im, gmf in imt_gmf:
            if im.string == 'PGV':
                pgv = gmf
            elif im.string == 'PGA':
                pga = gmf
            else:
                continue
        # Raise error if either PGA or PGV is missing
        if pga is None or pgv is None:
            raise ValueError("Both PGA and PGV are required to compute liquefaction probability using the RashidianBaise2020Liquefaction model")
        prob_liq, out_class, lse = rashidian_baise_2020(
            pga=pga, pgv=pgv, vs30=sites.vs30, dw=sites.dw, 
            wtd=sites.gwd, precip=sites.precip)
        out.append(prob_liq)
        out.append(out_class)
        out.append(lse)
        return out
    

class AllstadtEtAl2022Liquefaction(SecondaryPeril):
    """
    Computes the liquefaction probability from PGV and PGA and transforms it
    to binary output via the predefined probability threshold.
    """
    outputs = ["LiqProb","LiqOccur","LSE"]

    def __init__(self, intercept=8.801, pgv_coeff=0.334, vs30_coeff=-1.918, 
                 dw_coeff=-0.2054, wtd_coeff=-0.0333, precip_coeff=0.0005408):
        self.intercept = intercept
        self.pgv_coeff = pgv_coeff
        self.vs30_coeff = vs30_coeff
        self.dw_coeff = dw_coeff
        self.wtd_coeff = wtd_coeff
        self.precip_coeff = precip_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        pga = None
        pgv = None
        for im, gmf in imt_gmf:
            if im.string == 'PGV':
                pgv = gmf
            elif im.string == 'PGA':
                pga = gmf
            else:
                continue
        # Raise error if either PGA or PGV is missing
        if pga is None or pgv is None:
            raise ValueError("Both PGA and PGV are required to compute liquefaction probability using the AllstadtEtAl2022Liquefaction model")
        
        prob_liq, out_class, lse = allstadt_etal_2022(
            pga=pga, pgv=pgv, mag=mag, vs30=sites.vs30, dw=sites.dw, 
            wtd=sites.gwd, precip=sites.precip)
        out.append(prob_liq)
        out.append(out_class)
        out.append(lse)
        return out
    

class AkhlagiEtAl2021LiquefactionA(SecondaryPeril):
    """
    Computes the liquefaction probability from PGV and transforms it
    to binary output via the predefined probability threshold.
    """
    experimental = True
    outputs = ["LiqProb","LiqOccur"]

    def __init__(self, intercept=4.925, pgv_coeff=0.694, tri_coeff=-0.459, 
                 dc_coeff=-0.403, dr_coeff=-0.309, zwb_coeff=-0.164):
        self.intercept = intercept
        self.pgv_coeff = pgv_coeff
        self.tri_coeff = tri_coeff
        self.dc_coeff = dc_coeff
        self.dr_coeff = dr_coeff
        self.zwb_coeff = zwb_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGV':
                prob_liq, out_class = akhlagi_etal_2021_model_a(
                    pgv=gmf, tri=sites.tri, dc=sites.dc, 
                    dr=sites.dr, zwb=sites.zwb)
            out.append(prob_liq)
            out.append(out_class)
        return out
    

class AkhlagiEtAl2021LiquefactionB(SecondaryPeril):
    """
    Computes the liquefaction probability from PGV and transforms it
    to binary output via the predefined probability threshold.
    """
    experimental = True
    outputs = ["LiqProb","LiqOccur"]

    def __init__(self, intercept=9.504, pgv_coeff=0.706, vs30_coeff=-0.994, 
                 dc_coeff=-0.389, dr_coeff=-0.291, zwb_coeff=-0.205):
        self.intercept = intercept
        self.pgv_coeff = pgv_coeff
        self.vs30_coeff = vs30_coeff
        self.dc_coeff = dc_coeff
        self.dr_coeff = dr_coeff
        self.zwb_coeff = zwb_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGV':
                prob_liq, out_class = akhlagi_etal_2021_model_b(
                    pgv=gmf, vs30_coeff=sites.vs30_coeff, dc=sites.dc, 
                    dr=sites.dr, zwb=sites.zwb)
            out.append(prob_liq)
            out.append(out_class)
        return out


class Bozzoni2021LiquefactionEurope(SecondaryPeril):
    """
    Computes the liquefaction probability from PGA and transforms it
    to binary output via the predefined probability threshold.
    """
    outputs = ["LiqProb","LiqOccur"]

    def __init__(self, intercept=-11.489, pgam_coeff=3.864, cti_coeff=2.328, vs30_coeff=-0.091):
        self.intercept = intercept
        self.pgam_coeff = pgam_coeff
        self.cti_coeff = cti_coeff
        self.vs30_coeff = vs30_coeff

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGA':
                prob_liq, out_class = bozzoni_etal_2021_europe(
                    pga=gmf, mag=mag, cti=sites.cti, vs30=sites.vs30)
            out.append(prob_liq)
            out.append(out_class)
        return out


supported = [cls.__name__ for cls in SecondaryPeril.__subclasses__()]


class TodorovicSilva2022NonParametric(SecondaryPeril):
    """
    Computes the liquefaction probability from PGV and transforms it
    to binary output via the predefined probability threshold.
    """
    outputs = ["LiqOccur", "LiqProb"]

    def __init__(self):
        pass

    def prepare(self, sites):
        pass

    def compute(self, mag, imt_gmf, sites):
        out = []
        for im, gmf in imt_gmf:
            if im.string == 'PGV':
                out_class, out_prob = todorovic_silva_2022_nonparametric_general(
                    pgv=gmf, vs30=sites.vs30, dw=sites.dw, wtd=sites.gwd, precip=sites.precip)
            out.append(out_class)
            out.append(out_prob)
        return out


supported = [cls.__name__ for cls in SecondaryPeril.__subclasses__()]