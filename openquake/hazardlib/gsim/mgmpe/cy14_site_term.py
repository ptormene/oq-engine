# The Hazard Library
# Copyright (C) 2012-2020 GEM Foundation
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Module :mod:`openquake.hazardlib.mgmp.nrcan15_site_term` implements
:class:`~openquake.hazardlib.mgmpe.ask14_site_term.ASK14SiteTerm`
"""

import copy
import numpy as np
from openquake.hazardlib import const
from openquake.hazardlib.gsim.base import GMPE, registry
from openquake.hazardlib.gsim.chiou_youngs_2014 import ChiouYoungs2014


class CY14SiteTerm(GMPE):
    """
    Implements a modified GMPE class that can be used to account for local
    soil conditions in the estimation of ground motion.

    :param gmpe_name:
        The name of a GMPE class
    """

    # Parameters
    REQUIRES_SITES_PARAMETERS = {'vs30'}
    REQUIRES_DISTANCES = set()
    REQUIRES_RUPTURE_PARAMETERS = set()
    DEFINED_FOR_INTENSITY_MEASURE_COMPONENT = ''
    DEFINED_FOR_INTENSITY_MEASURE_TYPES = set()
    DEFINED_FOR_STANDARD_DEVIATION_TYPES = {const.StdDev.TOTAL}
    DEFINED_FOR_TECTONIC_REGION_TYPE = ''
    DEFINED_FOR_REFERENCE_VELOCITY = None

    def __init__(self, gmpe_name):
        super().__init__(gmpe_name=gmpe_name)
        self.gmpe = registry[gmpe_name]()
        self.set_parameters()
        #
        # Check if this GMPE has the necessary requirements
        if not (hasattr(self.gmpe, 'DEFINED_FOR_REFERENCE_VELOCITY') or
                'vs30' in self.gmpe.REQUIRES_SITES_PARAMETERS):
            msg = '{:s} does not use vs30 nor a defined reference velocity'
            raise AttributeError(msg.format(str(self.gmpe)))
        if 'vs30' not in self.gmpe.REQUIRES_SITES_PARAMETERS:
            self.REQUIRES_SITES_PARAMETERS = frozenset(
                self.gmpe.REQUIRES_SITES_PARAMETERS | {'vs30'})
        #
        # Check compatibility of reference velocity
        if hasattr(self.gmpe, 'DEFINED_FOR_REFERENCE_VELOCITY'):
            assert (self.gmpe.DEFINED_FOR_REFERENCE_VELOCITY >= 1100 and
                    self.gmpe.DEFINED_FOR_REFERENCE_VELOCITY <= 1160)

    def get_mean_and_stddevs(self, sites, rup, dists, imt, stds_types):
        """
        See :meth:`superclass method
        <.base.GroundShakingIntensityModel.get_mean_and_stddevs>`
        for spec of input and result values.
        """

        # Prepare sites
        sites_rock = copy.copy(sites)
        sites_rock.vs30 = np.ones_like(sites_rock.vs30) * 1130.

        # Compute mean and standard deviation using the original GMM. These
        # values are used as ground-motion values on reference rock conditions.
        # CHECK [MP]: The computed reference motion is equal to the one in the
        #             CY14 model
        mean, stddvs = self.gmpe.get_mean_and_stddevs(sites_rock, rup, dists,
                                                      imt, stds_types)

        # Compute the site term correction factor
        cy14 = ChiouYoungs2014()
        vs30 = sites.vs30
        fa = cy14._get_site_term(cy14.COEFFS[imt], vs30, mean)
        mean += fa

        return mean, stddvs
