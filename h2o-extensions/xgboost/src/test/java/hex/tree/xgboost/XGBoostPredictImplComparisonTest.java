package hex.tree.xgboost;

import hex.SplitFrame;
import hex.genmodel.utils.DistributionFamily;
import hex.genmodel.utils.IOUtils;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;
import water.*;
import water.fvec.Frame;

import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.Collection;

@RunWith(Parameterized.class)
public class XGBoostPredictImplComparisonTest extends TestUtil {

    @BeforeClass
    public static void setup() {
        stall_till_cloudsize(1);
    }

    @Parameterized.Parameters(name = "XGBoost(booster={0},distribution={1},response={2}")
    public static Collection<Object[]> data() {
        return Arrays.asList(new Object[][]{
            {"gbtree", "AUTO", "AGE"},
            {"gbtree", "bernoulli", "CAPSULE"},
            {"gbtree", "multinomial", "CAPSULE"},
            {"gbtree", "gaussian", "AGE"},
            {"gbtree", "gamma", "AGE"},
            {"gbtree", "poisson", "AGE"},
            {"gbtree", "tweedie", "AGE"},
            {"dart", "AUTO", "AGE"},
            {"dart", "bernoulli", "CAPSULE"},
            {"dart", "multinomial", "CAPSULE"},
            {"dart", "gaussian", "AGE"},
            {"dart", "gamma", "AGE"},
            {"dart", "poisson", "AGE"},
            {"dart", "tweedie", "AGE"},
            {"gblinear", "AUTO", "AGE"},
            {"gblinear", "bernoulli", "CAPSULE"},
            {"gblinear", "multinomial", "CAPSULE"},
            {"gblinear", "gaussian", "AGE"},
            {"gblinear", "gamma", "AGE"},
            {"gblinear", "poisson", "AGE"},
            {"gblinear", "tweedie", "AGE"}
        });
    }

    @Parameterized.Parameter
    public String booster;

    @Parameterized.Parameter(1)
    public String distribution;

    @Parameterized.Parameter(2)
    public String response;

    @Test
    public void testPredictionsAreSame() {
        Scope.enter();
        try {
            Frame tfr = Scope.track(parse_test_file("./smalldata/prostate/prostate.csv"));
            // define special columns
            Scope.track(tfr.replace(1, tfr.vecs()[1].toCategoricalVec()));   // Convert CAPSULE to categorical
            Scope.track(tfr.replace(3, tfr.vecs()[3].toCategoricalVec()));   // Convert RACE to categorical
            DKV.put(tfr);

            // split into train/test
            SplitFrame sf = new SplitFrame(tfr, new double[]{0.7, 0.3}, null);
            sf.exec().get();
            Key[] splits = sf._destination_frames;
            Frame trainFrame = Scope.track((Frame) splits[0].get());
            Frame testFrame = Scope.track((Frame) splits[1].get());

            Frame.CSVStreamParams csvStreamParams = new Frame.CSVStreamParams();
            try {
                IOUtils.copyStream(trainFrame.toCSV(csvStreamParams), new FileOutputStream("xgb_train.csv"));
            } catch (IOException e) {
                e.printStackTrace();
            }
            try {
                IOUtils.copyStream(testFrame.toCSV(csvStreamParams), new FileOutputStream("xgb_test.csv"));
            } catch (IOException e) {
                e.printStackTrace();
            }
            System.out.println("DONE WRITING FRAMES ---------------");
            System.out.println("---------------------------------");


            XGBoostModel.XGBoostParameters parms = new XGBoostModel.XGBoostParameters();
            parms._booster = XGBoostModel.XGBoostParameters.Booster.valueOf(booster);
            parms._distribution = DistributionFamily.valueOf(distribution);
            parms._ntrees = 10;
            parms._max_depth = 5;
            parms._train = trainFrame._key;
            parms._valid = testFrame._key;
            parms._response_column = response;

            XGBoostModel model = new hex.tree.xgboost.XGBoost(parms).trainModel().get();
            Scope.track_generic(model);

            System.setProperty("sys.ai.h2o.xgboost.predict.native.enable", "true");
            System.setProperty("sys.ai.h2o.xgboost.predict.native.type", "cpu_predictor");
            Frame predsNative = Scope.track(model.score(testFrame));
            System.setProperty("sys.ai.h2o.xgboost.predict.native.enable", "false");
            Frame predsJava = Scope.track(model.score(testFrame));

            assertFrameEquals(predsNative, predsJava, 1e-10, getRelDelta(parms));
        } finally {
            System.clearProperty("sys.ai.h2o.xgboost.predict.native.enable");
            System.clearProperty("sys.ai.h2o.xgboost.predict.native.type");
            Scope.exit();
        }
    }

    private Double getRelDelta(XGBoostModel.XGBoostParameters parms) {
        if (usesGpu(parms)) {
            // train/predict on gpu is non-deterministic
            return 1e-3;
        } else if ("gblinear".equals(booster)) {
            return 1e-6;
        } else {
            return null;
        }
    }

    public static boolean usesGpu(XGBoostModel.XGBoostParameters parms) {
        return parms._backend == XGBoostModel.XGBoostParameters.Backend.gpu ||
            (parms._backend == XGBoostModel.XGBoostParameters.Backend.auto &&
                XGBoost.hasGPU(H2O.CLOUD.members()[0], 0));
    }

}
