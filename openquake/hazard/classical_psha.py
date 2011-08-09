# -*- coding: utf-8 -*-

# Copyright (c) 2010-2011, GEM Foundation.
#
# OpenQuake is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# only, as published by the Free Software Foundation.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License version 3 for more details
# (a copy is included in the LICENSE file that accompanied this code).
#
# You should have received a copy of the GNU Lesser General Public License
# version 3 along with OpenQuake.  If not, see
# <http://www.gnu.org/licenses/lgpl-3.0.txt> for a copy of the LGPLv3 License.

"""
Collection of functions that compute stuff using
as input data produced with the classical psha method.
"""

import math
import numpy

from scipy.interpolate import interp1d
from scipy.stats.mstats import mquantiles

from openquake import kvs
from openquake.logs import LOG


QUANTILE_PARAM_NAME = "QUANTILE_LEVELS"
POES_PARAM_NAME = "POES_HAZARD_MAPS"


def compute_mean_curve(curves):
    """Compute a mean hazard curve.

    The input parameter is a list of arrays where each array
    contains just the y values of the corresponding hazard curve.
    """

    return numpy.array(curves).mean(axis=0)


def compute_quantile_curve(curves, quantile):
    """Compute a quantile hazard curve.

    The input parameter is a list of arrays where each array
    contains just the y values of the corresponding hazard curve.
    """
    result = []

    if len(numpy.array(curves).flat):
        result = mquantiles(curves, quantile, axis=0)[0]

    return result


def _acceptable(value):
    """Return true if the value taken from the configuration
    file is valid, false otherwise."""
    try:
        value = float(value)
        return value >= 0.0 and value <= 1.0

    except ValueError:
        return False


def poes_at(job_id, site, realizations):
    """Return all the json deserialized hazard curves for
    a single site (different realizations).

    :param job_id: the id of the job.
    :type job_id: integer
    :param site: site where the curves are computed.
    :type site: :py:class:`shapes.Site` object
    :param realizations: number of realizations.
    :type realizations: integer
    :returns: the hazard curves.
    :rtype: list of :py:class:`list` of :py:class:`float`
        containing the probability of exceedence for each realization
    """
    keys = [kvs.tokens.hazard_curve_poes_key(job_id, realization, site)
                for realization in xrange(realizations)]
    # get the probablity of exceedence for each curve in the site
    return kvs.mget_decoded(keys)


def _extract_values_from_config(job, param_name):
    """Extract the set of valid values from the configuration file."""
    values = []

    if job.has(param_name):
        raw_values = job.params[param_name].split()
        values = [float(x) for x in raw_values if _acceptable(x)]

    return values


def compute_mean_hazard_curves(job_id, sites, realizations):
    """Compute a mean hazard curve for each site in the list
    using as input all the pre-computed curves for different realizations."""
    keys = []
    for site in sites:
        poes = poes_at(job_id, site, realizations)

        mean_poes = compute_mean_curve(poes)

        key = kvs.tokens.mean_hazard_curve_key(job_id, site)
        keys.append(key)

        kvs.set_value_json_encoded(key, mean_poes)

    return keys


def compute_quantile_hazard_curves(job_id, sites, realizations, quantiles):
    """Compute a quantile hazard curve for each site in the list
    using as input all the pre-computed curves for different realizations.

    The QUANTILE_LEVELS parameter in the configuration file specifies
    all the values used in the computation.
    """

    LOG.debug("[QUANTILE_HAZARD_CURVES] List of quantiles is %s" % quantiles)

    keys = []
    for site in sites:
        poes = poes_at(job_id, site, realizations)

        for quantile in quantiles:
            quantile_poes = compute_quantile_curve(poes, quantile)

            key = kvs.tokens.quantile_hazard_curve_key(
                    job_id, site, quantile)
            keys.append(key)

            kvs.set_value_json_encoded(key, quantile_poes)

    return keys


def build_interpolator(poes, imls):
    poes = numpy.array(poes)[::-1]
    imls = numpy.log(numpy.array(imls)[::-1])

    interpolator = interp1d(poes, imls, kind='linear')

    def safe_interpolator(poe, site=None):
        if poe > poes[-1]:
            LOG.debug("[HAZARD_MAP] Interpolation out of bounds for PoE %s, "\
                "using maximum PoE value pair, PoE: %s, IML: %s, at site %s" % (
                poe, poes[-1], math.exp(imls[-1]), site))
            return math.exp(imls[-1])

        if poe < poes[0]:
            LOG.debug("[HAZARD_MAP] Interpolation out of bounds for PoE %s, "\
                "using minimum PoE value pair, PoE: %s, IML: %s, at site %s" % (
                poe, poes[0], math.exp(imls[0]), site))
            return math.exp(imls[0])

        return math.exp(interpolator(poe))

    return safe_interpolator


def compute_quantile_hazard_maps(job_id, sites, quantiles, imls, desired_poes):
    """Compute quantile hazard maps using as input all the
    pre computed quantile hazard curves.

    The POES_HAZARD_MAPS parameter in the configuration file specifies
    all the values used in the computation.
    """

    LOG.debug("[QUANTILE_HAZARD_MAPS] List of POEs is %s" % desired_poes)
    LOG.debug("[QUANTILE_HAZARD_MAPS] List of quantiles is %s" % quantiles)

    keys = []
    for quantile in quantiles:
        LOG.debug("[QUANTILE_HAZARD_MAPS] Found %s pre computed " \
                "quantile curves for quantile %s"
                % (len(sites), quantile))

        for site in sites:
            quantile_poes = kvs.get_value_json_decoded(kvs.tokens.quantile_hazard_curve_key(job_id, site, quantile))

            interpolate = build_interpolator(quantile_poes, imls)

            for poe in desired_poes:
                key = kvs.tokens.quantile_hazard_map_key(
                        job_id, site, poe, quantile)
                keys.append(key)

                kvs.set_value_json_encoded(key, interpolate(poe, site))

    return keys


def compute_mean_hazard_maps(job_id, sites, imls, desired_poes):
    """Compute mean hazard maps using as input all the
    pre computed mean hazard curves.

    The POES_HAZARD_MAPS parameter in the configuration file specifies
    all the values used in the computation.
    """

    LOG.debug("[MEAN_HAZARD_MAPS] List of POEs is %s" % desired_poes)
    LOG.debug("[MEAN_HAZARD_MAPS] Found %s pre computed mean curves" % len(sites))

    keys = []
    for site in sites:
        mean_poes = kvs.get_value_json_decoded(kvs.tokens.mean_hazard_curve_key(job_id, site))
        interpolate = build_interpolator(mean_poes, imls)

        for poe in desired_poes:
            key = kvs.tokens.mean_hazard_map_key(job_id, site, poe)
            keys.append(key)

            kvs.set_value_json_encoded(key, interpolate(poe, site))

    return keys
