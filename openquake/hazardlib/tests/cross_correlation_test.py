# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (C) 2021, GEM Foundation
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

import unittest
import numpy
from numpy.testing import assert_allclose as aac
from openquake.hazardlib.imt import PGA, SA
from openquake.hazardlib.cross_correlation import (
    BakerJayaram2008, GodaAtkinson2009)


class BakerJayaram2008Test(unittest.TestCase):
    """
    Tests the implementation of the Baker and Jayaram (2008) model. For the
    testing we use the original matlab implementation available at:
    https://web.stanford.edu/~bakerjw/GMPEs.html
    """

    def _test(self, imt_from, imt_to, expected):
        computed = self.cm.get_correlation(imt_from, imt_to)
        msg = 'The computed correlation coefficient is wrong'
        self.assertAlmostEqual(computed, expected, places=7, msg=msg)

    def setUp(self):
        self.cm = BakerJayaram2008()

    def test_01(self):
        imt_from = SA(0.1)
        imt_to = SA(0.5)
        expected = 0.4745240873
        self._test(imt_from, imt_to, expected)

    def test_02(self):
        imt_from = SA(0.15)
        imt_to = SA(0.5)
        expected = 0.5734688765
        self._test(imt_from, imt_to, expected)

    def test_03(self):
        imt_from = SA(0.05)
        imt_to = SA(0.15)
        expected = 0.9153049738
        self._test(imt_from, imt_to, expected)

    def test_04(self):
        imt_from = SA(0.05)
        imt_to = SA(0.10)
        expected = 0.9421213925
        self._test(imt_from, imt_to, expected)


class GodaAtkinson2009Test(unittest.TestCase):
    """
    Tests the implementation of the Goda and Atkinson (2009) model.
    """
    def setUp(self):
        self.cm = GodaAtkinson2009()
        self.imts = [PGA(), SA(0.3), SA(0.6), SA(1.0)]

    def test(self):
        corma = self.cm._get_correlation_matrix(self.imts)
        aac(corma,
            numpy.array([[1.        , 0.71678166, 0.41330149, 0.23046633],
                         [0.71678166, 1.        , 0.83261724, 0.68322083],
                         [0.41330149, 0.83261724, 1.        , 0.88167281],
                         [0.23046633, 0.68322083, 0.88167281, 1.        ]]))

        numpy.random.seed(42)
        eps = self.cm.get_inter_eps(self.imts, 2)
        aac(eps, numpy.array([[-0.606248, -0.134417, -0.667341, -0.35735 ],
                              [-0.306698,  0.62123 ,  0.284299,  0.035089]]),
            rtol=1e-5)
