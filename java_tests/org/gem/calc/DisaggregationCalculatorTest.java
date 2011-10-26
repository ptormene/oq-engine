package org.gem.calc;

import static org.junit.Assert.*;

import java.util.Arrays;

import org.gem.hdf5.HDF5Util;
import org.junit.Test;
import org.opensha.commons.data.function.DiscretizedFuncAPI;
import org.opensha.commons.geo.Location;
import org.opensha.commons.geo.LocationList;
import org.opensha.sha.earthquake.rupForecastImpl.GEM1.GEM1ERF;
import org.opensha.sha.util.TectonicRegionType;

import static org.gem.calc.DisaggregationTestHelper.*;
import static org.gem.calc.DisaggregationCalculator.digitize;
import static org.gem.calc.DisaggregationCalculator.closestLocation;
import static org.gem.calc.DisaggregationCalculator.inRange;
import static org.gem.calc.DisaggregationCalculator.getGMV;
import static org.gem.calc.DisaggregationCalculator.normalize;
import static org.gem.calc.DisaggregationCalculator.assertPoissonian;
import static org.gem.calc.DisaggregationCalculator.assertNonZeroStdDev;

public class DisaggregationCalculatorTest
{

    /**
     * If any of the bin edges passed to the constructor are null,
     * an IllegalArgumentException should be thrown.
     */
    @Test(expected=IllegalArgumentException.class)
    public void testConstructorOneNull()
    {
        new DisaggregationCalculator(
                new Double[10], new Double[10], null,
                new Double[10]);
    }

    /**
     * Same the test above, except with all null input.
     */
    @Test(expected=IllegalArgumentException.class)
    public void testConstructorManyNull()
    {
        new DisaggregationCalculator(null, null, null, null);
    }

    /**
     * If any of the bin edges passed to the constructor have a length < 2,
     * an IllegalArgumentException should be thrown.
     */
    @Test(expected=IllegalArgumentException.class)
    public void testConstructorOneTooShort()
    {
        new DisaggregationCalculator(
                new Double[2], new Double[2], new Double[1],
                new Double[2]);
    }

    /**
     * Same as the test above, except all input arrays are too short.
     */
    @Test(expected=IllegalArgumentException.class)
    public void testConstructorAllTooShort()
    {
        new DisaggregationCalculator(
                new Double[1], new Double[1], new Double[1],
                new Double[1]);
    }

    @Test(expected=IllegalArgumentException.class)
    public void testConstructorUnsortedBinEdges()
    {
        Double[] unsorted = {1.1, 1.0};
        new DisaggregationCalculator(
                LAT_BIN_LIMS, LON_BIN_LIMS, unsorted,
                EPS_BIN_LIMS);
    }

    /**
     * Test constructor with known-good input.
     * (No errors should be thrown.)
     */
    @Test
    public void testConstructorGoodInput()
    {
        new DisaggregationCalculator(
                LAT_BIN_LIMS, LON_BIN_LIMS, MAG_BIN_LIMS,
                EPS_BIN_LIMS);
    }

    @Test
    public void testComputeMatrix()
    {
        DisaggregationCalculator disCalc = new DisaggregationCalculator(
                LAT_BIN_LIMS, LON_BIN_LIMS, MAG_BIN_LIMS,
                EPS_BIN_LIMS);

        GEM1ERF erf = makeTestERF();

        double minMag = (Double) erf.getParameter(GEM1ERF.MIN_MAG_NAME).getValue();

        double[][][][][] result = disCalc.computeMatrix(
                makeTestSite(), erf, makeTestImrMap(), POE,
                makeHazardCurve(), minMag).getMatrix();

        // The expected results were generated by code independent of this
        // calculator. This level of tolerance (delta of 10^-5) is reasonable.
        assertArrayEquals(EXPECTED, result, 0.00001);
    }

    /**
     * Test for the simplified computeMatrix method (basically, with more
     * primitive input).
     *
     * The results should be same as the other computeMatrix method;
     * this is just to exercise different (but equivalent) input.
     *
     * The reason we want to test this is because a more primitive
     * method is easier to call through the Python-Java bridge.
     */
    @Test
    public void testComputeMatrix2()
    {
        DisaggregationCalculator disCalc = new DisaggregationCalculator(
                LAT_BIN_LIMS, LON_BIN_LIMS, MAG_BIN_LIMS,
                EPS_BIN_LIMS);

        GEM1ERF erf = makeTestERF();

        double lat, lon, vs30Value, depthTo2pt5;
        lat = 0.0;
        lon = 0.0;
        vs30Value = 760.0;
        depthTo2pt5 = 1.0;
        double[][][][][] result = disCalc.computeMatrix(
                lat, lon, erf, makeTestImrMap(), POE, IMLS, vs30Value,
                depthTo2pt5).getMatrix();

        // The expected results were generated by code independent of this
        // calculator. This level of tolerance (delta of 10^-5) is reasonable.
        assertArrayEquals(EXPECTED, result, 0.00001);
    }

    /**
     * Compute the matrix and write it to an HDF5 file. The result of this will
     * give us a file path to the HDF5 file; read the matrix from the file and
     * check the results.
     * @throws Exception
     */
    @Test
    public void testComputeAndWriteMatrix() throws Exception
    {
        DisaggregationCalculator disCalc = new DisaggregationCalculator(
                LAT_BIN_LIMS, LON_BIN_LIMS, MAG_BIN_LIMS,
                EPS_BIN_LIMS);

        GEM1ERF erf = makeTestERF();

        double lat, lon, vs30Value, depthTo2pt5;
        lat = 0.0;
        lon = 0.0;
        vs30Value = 760.0;
        depthTo2pt5 = 1.0;

        DisaggregationResult result = disCalc.computeAndWriteMatrix(
                lat, lon, erf, makeTestImrMap(), POE, IMLS, vs30Value,
                depthTo2pt5, "/tmp");

        // sanity check; make sure the matrix is correct
        // this is not the primary test of this test case
        assertArrayEquals(EXPECTED, result.getMatrix(), 0.00001);

        // primary test: read the matrix from the hdf5 file (from the path given
        // in the results) and check it against the expected results
        double[][][][][] fromFile = HDF5Util.readMatrix(result.getMatrixPath());

        assertArrayEquals(EXPECTED, fromFile, 0.00001);
    }

    private static void assertArrayEquals(
            double[][][][][] expected,
            double[][][][][] actual,
            double delta) {
        for (int i = 0; i < expected.length; i++)
        {
            for (int j = 0; j < expected[i].length; j++)
            {
                for (int k = 0; k < expected[i][j].length; k++)
                {
                    for (int l = 0; l < expected[i][j][k].length; l++)
                    {
                        for (int m = 0; m < expected[i][j][k][l].length; m++)
                        {
                            double e = expected[i][j][k][l][m];
                            double a = actual[i][j][k][l][m];
                            assertEquals(e, a, delta);
                        }
                    }
                }
            }
        }
    }

    @Test
    public void testDigitize()
    {
        int expected = 3;

        int actual = digitize(MAG_BIN_LIMS, 8.9);

        assertEquals(expected, actual);
    }

    @Test(expected=IllegalArgumentException.class)
    public void testDigitizeOutOfRange()
    {
        digitize(MAG_BIN_LIMS, 4.9);
    }

    @Test
    public void testGetBinIndices()
    {
        DisaggregationCalculator disCalc = new DisaggregationCalculator(
                LAT_BIN_LIMS, LON_BIN_LIMS, MAG_BIN_LIMS,
                EPS_BIN_LIMS);

        int[] expected = {0, 2, 1, 6, 3};
        double lat, lon, mag, epsilon;
        lat = -0.6;
        lon = 0.0;
        mag = 6.5;
        epsilon = 3.49;
        TectonicRegionType trt = TectonicRegionType.SUBDUCTION_SLAB;

        int[] actual = disCalc.getBinIndices(lat, lon, mag, epsilon, trt);

        assertTrue(Arrays.equals(expected, actual));
    }

    @Test(expected=IllegalArgumentException.class)
    public void testGetBinIndicesOutOfRange()
    {
        DisaggregationCalculator disCalc = new DisaggregationCalculator(
                LAT_BIN_LIMS, LON_BIN_LIMS, MAG_BIN_LIMS,
                EPS_BIN_LIMS);

        double lat, lon, mag, epsilon;
        lat = -0.6;
        lon = 0.0;
        mag = 6.5;
        epsilon = 3.5;  // out of range
        TectonicRegionType trt = TectonicRegionType.SUBDUCTION_SLAB;

        disCalc.getBinIndices(lat, lon, mag, epsilon, trt);
    }

    @Test
    public void testClosestLocation()
    {
        Location target = new Location(90.0, 180.0);

        LocationList locList = new LocationList();
        Location loc1, loc2, loc3;
        loc1 = new Location(0.0, 0.0);
        loc2 = new Location(90.0, 179.9);
        loc3 = new Location(90.0, -180.0);
        locList.add(loc1);
        locList.add(loc2);
        locList.add(loc3);

        assertEquals(loc3, closestLocation(locList, target));
    }

    @Test
    public void testInRange()
    {
        Double[] bins = {10.0, 20.0, 30.0};

        // boundaries:
        assertTrue(inRange(bins, 10.0));
        assertFalse(inRange(bins, 30.0));

        // in range:
        assertTrue(inRange(bins, 29.9));

        // out of range
        assertFalse(inRange(bins, 31.0));
    }

    @Test
    public void testGetGMV()
    {
        // technically, this is an invalid PoE value
        // we're just using this to test boundary behavior of getGMV
        // (since the highest PoE on this test curve is 1.0--the max valid value)
        Double highPoe = 1.1;
        // slightly lower than the lowest PoE in the test curve
        Double lowPoe = 2.5607144e-05;

        Double minIml = -5.298317366548036;  // log(0.005)
        Double maxIml = 0.7561219797213337;  // log(2.13)
        // expected interpolated value for poe = 0.5
        Double imlForPoe0_5 = -2.2754844247554944;

        DiscretizedFuncAPI hazardCurve = makeHazardCurve();

        double delta = 0.0001;
        // boundary tests:
        assertEquals(minIml, getGMV(hazardCurve, highPoe), delta);
        assertEquals(maxIml, getGMV(hazardCurve, lowPoe), delta);

        // interpolation test:
        assertEquals(imlForPoe0_5, getGMV(hazardCurve, 0.5), delta);
    }

    @Test
    public void testNormalize()
    {
        double[][][][][] input =
            {
                {
                    {
                        {{0, 5.0}, {0, 0}},
                        {{0, 0}, {0, 0}}
                    },
                    {
                        {{0, 0}, {0, 0}},
                        {{0, 0}, {0, 0}}
                    }
                },
                {
                    {
                        {{0, 0}, {10.0, 0}},
                        {{0, 0}, {0, 0}}
                    },
                    {
                        {{0, 0}, {0, 0}},
                        {{0, 25.0}, {0, 0}}
                    }
                }
            };
        double normFactor = 40.0;  // the sum of all values in the matrix

        double[][][][][] expected =
            {
                {
                    {
                        {{0, 0.125}, {0, 0}},
                        {{0, 0}, {0, 0}}
                    },
                    {
                        {{0, 0}, {0, 0}},
                        {{0, 0}, {0, 0}}
                    }
                },
                {
                    {
                        {{0, 0}, {0.25, 0}},
                        {{0, 0}, {0, 0}}
                    },
                    {
                        {{0, 0}, {0, 0}},
                        {{0, 0.625}, {0, 0}}
                    }
                }
            };

        assertTrue(Arrays.deepEquals(expected, normalize(input, normFactor)));
    }

    @Test
    public void testAssertPoissonian()
    {
        // This should succeed without any errors.
        assertPoissonian(makeTestERF());
    }

    @Test(expected=RuntimeException.class)
    public void testAssertPoissonianBadData()
    {
        assertPoissonian(new NonPoissonianERF());
    }

    @Test
    public void testAssertNonZeroStdDev()
    {
        assertNonZeroStdDev(makeTestImrMap());
    }

    @Test(expected=RuntimeException.class)
    public void testAssertNonZeroStdDevBadData()
    {
        assertNonZeroStdDev(makeTestImrMapZeroStdDev());
    }
}
