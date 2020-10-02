# -*- encoding: utf-8 -*-

import random
from contextlib import contextmanager
from collections import OrderedDict, Counter

import h2o
import numpy as np
import matplotlib
import matplotlib.colors
import matplotlib.figure

try:
    import matplotlib.pyplot as plt
except ImportError:
    # Possibly failed due to missing tkinter in old matplotlib in python 2.7
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt


def _display(object):
    """
    Display the object.
    :param object: An object to be displayed.
    :return: the input
    """
    if isinstance(object, matplotlib.figure.Figure) and matplotlib.get_backend().lower() != "agg":
        plt.show()
    else:
        try:
            import IPython.display
            IPython.display.display(object)
        except ImportError:
            print(object)
    if isinstance(object, matplotlib.figure.Figure):
        plt.close(object)
    return object


def _dont_display(object):
    """
    Don't display the object
    :param object: that should not be displayed
    :return: input
    """
    if isinstance(object, matplotlib.figure.Figure):
        plt.close()
    return object


# UTILS
class Header:
    """
    Class representing a Header with pretty printing for IPython.
    """

    def __init__(self, content, level=1):
        self.content = content
        self.level = level

    def _repr_html_(self):
        return "<h{level}>{content}</h{level}>".format(level=self.level, content=self.content)

    def _repr_markdown_(self):
        return "\n\n{} {}".format("#" * self.level, self.content)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))

    def __str__(self):
        return self._repr_markdown_()


class Description:
    """
    Class representing a Description with pretty printing for IPython.
    """
    DESCRIPTIONS = dict(
        leaderboard="Leaderboard shows models with their metrics. When provided with H2OAutoML object, "
                    "the leaderboard shows 5-fold cross-validated metrics by default (depending on the "
                    "H2OAutoML settings), otherwise it shows metrics computed on the frame.",
        leaderboard_row="Leaderboard shows models with their metrics and their predictions for a given row. "
                        "When provided with H2OAutoML object, the leaderboard shows 5-fold cross-validated "
                        "metrics by default (depending on the H2OAutoML settings), otherwise it shows "
                        "metrics computed on the frame.",
        confusion_matrix="Confusion matrix shows a predicted class vs an actual class.",
        residual_analysis="Residual analysis plot shows residuals vs fitted values. "
                          "Ideally, residuals should be randomly distributed. Patterns in this plot can indicate "
                          "potential problems with the model selection, e.g., using simpler model than necessary, "
                          "not accounting for heteroscedasticity, autocorrelation etc.",
        variable_importance="Variable importance shows how much do the predictions depend on what variable.",
        variable_importance_heatmap="Variable importance heatmap shows variable importances on multiple models. "
                                    "By default, the models and variables are ordered by their similarity.",
        model_correlation_heatmap="Model correlation matrix shows correlation between prediction of the models. "
                                  "For classification, frequency of same predictions is used. By default, models "
                                  "are ordered by their similarity.",
        shap_summary="SHAP summary plot shows contribution of features for each instance. The sum "
                     "of the feature contributions and the bias term is equal to the raw prediction "
                     "of the model, i.e., prediction before applying inverse link function.",
        pdp="Partial dependence plot (PDP) gives a graphical depiction of the marginal effect of a variable "
            "on the response. The effect of a variable is measured in change in the mean response. "
            "PDP assumes independence between the feature for which is the PDP computed and the rest.",
        ice="Individual conditional expectations (ICE) plot gives a graphical depiction of the marginal "
            "effect of a variable on the response. ICE plot is similar to partial dependence plot (PDP), "
            "PDP shows the average effect of a feature while ICE plot shows the effect for a single "
            "instance. The following plot shows the effect for each decile. "
            "In contrast to partial dependence plot, ICE plot can provide more insight especially when "
            "there is stronger feature interaction.",
        ice_row="Individual conditional expectations (ICE) plot gives a graphical depiction of the marginal "
                "effect of a variable on the response for a given row. ICE plot is similar to partial "
                "dependence plot (PDP), PDP shows the average effect of a feature while ICE plot shows "
                "the effect for a single instance.",
        shap_explain_row="SHAP explanation shows contribution of features for a given instance. The sum "
                         "of the feature contributions and the bias term is equal to the raw prediction "
                         "of the model, i.e., prediction before applying inverse link function. H2O implements "
                         "TreeSHAP which when the features are correlated, can increase contribution of a feature "
                         "that had no influence on the prediction.",
    )

    def __init__(self, for_what):
        self.content = self.DESCRIPTIONS[for_what]

    def _repr_html_(self):
        return "<blockquote>{}</blockquote>".format(self.content)

    def _repr_markdown_(self):
        return "\n> {}".format(self.content)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))

    def __str__(self):
        return self._repr_markdown_()


class H2OExplanation(OrderedDict):
    def _ipython_display_(self):
        from IPython.display import display
        for v in self.values():
            display(v)


@contextmanager
def no_progress():
    """
    A context manager that temporarily blocks showing the H2O's progress bar.
    Used when a multiple models are evaluated.
    """
    progress = h2o.job.H2OJob.__PROGRESS_BAR__
    if progress:
        h2o.no_progress()
    yield
    if progress:
        h2o.show_progress()


class NumpyFrame:
    """
    Simple class that very vaguely emulates Pandas DataFrame.
    Main purpose is to keep parsing from the List of Lists format to numpy.
    This class is meant to be used just in the explain module.
    Due to that fact it encodes the factor variables similarly to R/pandas -
    factors are mapped to numeric column which in turn makes it easier to plot it.
    """

    def __init__(self, h2o_frame):
        # type: ("NumpyFrame", Union[h2o.H2OFrame, h2o.two_dim_table.H2OTwoDimTable]) -> None
        if isinstance(h2o_frame, h2o.two_dim_table.H2OTwoDimTable):
            self._columns = h2o_frame.col_header
            _is_numeric = np.array([type_ in ["double", "float", "long", "integer"]
                                    for type_ in h2o_frame.col_types], dtype=bool)
            _is_factor = np.array([type_ in ["string"] for type_ in h2o_frame.col_types],
                                  dtype=bool)
            df = h2o_frame.cell_values
            self._factors = dict()
            for col in range(len(self._columns)):
                if _is_factor[col]:
                    levels = set(row[col] for row in df)
                    self._factors[self._columns[col]] = list(levels)

            self._data = np.empty((len(df), len(self._columns)))
            df = [self._columns] + df
        elif isinstance(h2o_frame, h2o.H2OFrame):
            _is_factor = np.array(h2o_frame.isfactor(), dtype=np.bool) | np.array(
                h2o_frame.ischaracter(), dtype=np.bool)
            _is_numeric = h2o_frame.isnumeric()
            self._columns = h2o_frame.columns
            self._factors = {col: h2o_frame[col].asfactor().levels()[0] for col in
                             np.array(h2o_frame.columns)[_is_factor]}

            df = h2o_frame.as_data_frame(False)
            self._data = np.empty((h2o_frame.nrow, h2o_frame.ncol))
        else:
            raise RuntimeError("Unexpected type of \"h2o_frame\": {}".format(type(h2o_frame)))

        for idx, col in enumerate(df[0]):
            if _is_factor[idx]:
                convertor = self.from_factor_to_num(col)
                self._data[:, idx] = np.array(
                    [float(convertor.get(
                        row[idx] if not (len(row) == 0 or row[idx] == "") else "nan", "nan"))
                        for row in df[1:]], dtype=np.float32)
            elif _is_numeric[idx]:
                self._data[:, idx] = np.array(
                    [float(row[idx] if not (len(row) == 0 or row[idx] == "") else "nan") for row in
                     df[1:]],
                    dtype=np.float32)
            else:
                try:
                    self._data[:, idx] = np.array([row[idx] if not (len(row) == 0 or row[idx] == "")
                                                   else "nan" for row in df[1:]],
                                                  dtype=np.datetime64)
                except Exception:
                    raise RuntimeError("Unexpected type of column {}!".format(col))

    def isfactor(self, column):
        # type: ("NumpyFrame", str) -> bool
        """
        Is column a factor/categorical column?

        :param column: string containing the column name
        :return: boolean
        """
        return column in self._factors or self._get_column_and_factor(column)[0] in self._factors

    def from_factor_to_num(self, column):
        # type: ("NumpyFrame", str) -> Dict[str, int]
        """
        Get a dictionary mapping a factor to its numerical representation in the NumpyFrame

        :param column: string containing the column name
        :return: dictionary
        """
        fact = self._factors[column]
        return dict(zip(fact, range(len(fact))))

    def from_num_to_factor(self, column):
        # type: ("NumpyFrame", str) -> Dict[int, str]
        """
        Get a dictionary mapping numerical representation of a factor to the category names.

        :param column: string containing the column name
        :return: dictionary
        """
        fact = self._factors[column]
        return dict(zip(range(len(fact)), fact))

    def _get_column_and_factor(self, column):
        # type: ("NumpyFrame", str) -> Tuple[str, Optional[float]]
        """
        Get a column name and possibly a factor name.
        This is used to get proper column name and factor name when provided
        with the output of some algos such as XGBoost which encode factor
        columns to "column_name.category_name".

        :param column: string containing the column name
        :return: tuple (column_name: str, factor_name: Optional[str])
        """
        if column in self.columns:
            return column, None
        if column.endswith(".") and column[:-1] in self.columns:
            return column[:-1], None

        col_parts = column.split(".")
        for i in range(1, len(col_parts) + 1):
            if ".".join(col_parts[:i]) in self.columns:
                column = ".".join(col_parts[:i])
                factor_name = ".".join(col_parts[i:])
                if factor_name == "missing(NA)":
                    factor = float("nan")
                else:
                    factor = self.from_factor_to_num(column)[factor_name]
                return column, factor

    def __getitem__(self, indexer):
        # type: ("NumpyFrame", Union[str, Tuple[Union[int,List[int]], str]]) -> np.ndarray
        """
        A low level way to get a column or a row within a column.
        NOTE: Returns numeric representation even for factors.

        :param indexer: string for the whole column or a tuple (row_index, column_name)
        :return: a column or a row within a column
        """
        row = slice(None)
        if isinstance(indexer, tuple):
            row = indexer[0]
            column = indexer[1]
        else:
            column = indexer

        if column not in self.columns:
            column, factor = self._get_column_and_factor(column)
            if factor is not None:
                if factor != factor:
                    return np.asarray(np.isnan(self._data[row, self.columns.index(column)]),
                                      dtype=np.float32)
                return np.asarray(self._data[row, self.columns.index(column)] == factor,
                                  dtype=np.float32)
        return self._data[row, self.columns.index(column)]

    def get(self, column, as_factor=True):
        # type: ("NumpyFrame", str, bool) -> np.ndarray
        """
        Get a column.

        :param column: string containing the column name
        :param as_factor: if True (default), factor column will contain string
                          representation; otherwise numerical representation
        :return: A column represented as numpy ndarray
        """
        if as_factor and self.isfactor(column):
            column, factor_idx = self._get_column_and_factor(column)
            if factor_idx is not None:
                return self[column] == factor_idx
            convertor = self.from_num_to_factor(column)
            return np.array([convertor.get(row, "") for row in self[column]])
        return self[column]

    def levels(self, column):
        # type: ("NumpyFrame", str) -> List[str]
        """
        Get levels/categories of a factor column.

        :param column: a string containing the column name
        :return: list of levels
        """
        return self._factors.get(column, [])

    def nlevels(self, column):
        # type: ("NumpyFrame", str) -> int
        """
        Get number of levels/categories of a factor column.

        :param column: string containing the column name
        :return: a number of levels within a factor
        """
        return len(self.levels(column))

    @property
    def columns(self):
        # type: ("NumpyFrame") -> List[str]
        """
        Column within the NumpyFrame.

        :return: list of columns
        """
        return self._columns

    @property
    def nrow(self):
        # type: ("NumpyFrame") -> int
        """
        Number of rows.

        :return: number of rows
        """
        return self._data.shape[0]

    @property
    def ncol(self):
        # type: ("NumpyFrame") -> int
        """
        Number of columns.

        :return: number of columns
        """
        return self._data.shape[1]

    @property
    def shape(self):
        # type: ("NumpyFrame") -> Tuple[int, int]
        """
        Shape of the frame.

        :return: tuple (number of rows, number of columns)
        """
        return self._data.shape

    def sum(self, axis=0):
        # type: ("NumpyFrame", int) -> np.ndarray
        """
        Calculate the sum of the NumpyFrame elements over the given axis.

        WARNING: This method doesn't care if the column is categorical or numeric. Use with care.

        :param axis: Axis along which a sum is performed.
        :return: numpy.ndarray with shape same as NumpyFrame with the `axis` removed
        """
        return self._data.sum(axis=axis)

    def mean(self, axis=0):
        # type: ("NumpyFrame", int) -> np.ndarray
        """
        Calculate the mean of the NumpyFrame elements over the given axis.

        WARNING: This method doesn't care if the column is categorical or numeric. Use with care.

        :param axis: Axis along which a mean is performed.
        :return: numpy.ndarray with shape same as NumpyFrame with the `axis` removed
        """
        return self._data.mean(axis=axis)

    def items(self, with_categorical_names=False):
        # type: ("NumpyFrame", bool) -> Generator[Tuple[str, np.ndarray], None, None]
        """
        Make a generator that yield column name and ndarray with values.

        :params with_categorical_names: if True, factor columns are returned as string columns;
                                        otherwise numerical
        :return: generator to be iterated upon
        """
        for col in self.columns:
            yield col, self.get(col, with_categorical_names)


def _shorten_model_ids(model_ids):
    import re
    regexp = re.compile("(.*)_AutoML_\\d{8}_\\d{6}(.*)")
    shortened_model_ids = [regexp.sub("\\1\\2", model_id) for model_id in model_ids]
    if len(set(shortened_model_ids)) == len(set(model_ids)):
        return shortened_model_ids
    return model_ids


def _get_algorithm(model,  treat_xrt_as_algorithm=False):
    # type: (Union[str, h2o.model.ModelBase], bool) -> str
    """
    Get algorithm type. Use model id to infer it if possible.
    :param model: model or a model_id
    :param treat_xrt_as_algorithm: boolean used for best_of_family
    :return: string containing algorithm name
    """
    if not isinstance(model, h2o.model.ModelBase):
        import re
        algo = re.search("^(DeepLearning|DRF|GAM|GBM|GLM|NaiveBayes|StackedEnsemble|RuleFit|XGBoost|XRT)(?=_)", model)
        if algo is not None:
            algo = algo.group(0).lower()
            if algo == "xrt" and not treat_xrt_as_algorithm:
                algo = "drf"
            return algo
        else:
            model = h2o.get_model()
    if treat_xrt_as_algorithm and model.algo == "drf":
        if model.actual_params.get("histogram_type") == "Random":
            return "xrt"
    return model.algo


def _first_of_family(models, all_stackedensembles=True):
    # type: (Union[str, h2o.model.ModelBase], bool) -> Union[str, h2o.model.ModelBase]
    """
    Get first of family models
    :param models: models or model ids
    :param all_stackedensembles: if True return all stacked ensembles
    :return: list of models or model ids (the same type as on input)
    """
    selected_models = []
    included_families = set()
    for model in models:
        family = _get_algorithm(model, treat_xrt_as_algorithm=True)
        if family not in included_families or (all_stackedensembles and "stackedensemble" == family):
            selected_models.append(model)
            included_families.add(family)
    return selected_models


def _density(xs, bins=100):
    # type: (np.ndarray, int) -> np.ndarray
    """
    Make an approximate density estimation by blurring a histogram (used for SHAP summary plot).
    :param xs: numpy vector
    :param bins: number of bins
    :return: density values
    """
    hist = list(np.histogram(xs, bins=bins))
    # gaussian blur
    hist[0] = np.convolve(hist[0],
                          [0.00598, 0.060626, 0.241843,
                           0.383103,
                           0.241843, 0.060626, 0.00598])[3:-3]
    hist[0] = hist[0] / np.max(hist[0])
    hist[1] = (hist[1][:-1] + hist[1][1:]) / 2
    return np.interp(xs, hist[1], hist[0])


def _uniformize(data, col_name):
    # type: (NumpyFrame, str) -> np.ndarray
    """
    Convert to quantiles.
    :param data: NumpyFrame
    :param col_name: string containing a column name
    :return: quantile values of individual points in the column
    """
    if col_name not in data.columns or data.isfactor(col_name):
        res = data[col_name]
        diff = (np.nanmax(res) - np.nanmin(res))
        if diff <= 0 or np.isnan(diff):
            return res
        res = (res - np.nanmin(res)) / diff
        return res

    col = data[col_name]
    xs = np.linspace(0, 1, 100)
    quantiles = np.nanquantile(col, xs)
    res = np.interp(col, quantiles, xs)
    res = (res - np.nanmin(res)) / (np.nanmax(res) - np.nanmin(res))
    return res


# PLOTS
def shap_summary_plot(
        model,  # type: h2o.model.ModelBase
        frame,  # type: h2o.H2OFrame
        columns=None,  # type: Optional[Union[List[int], List[str]]]
        top_n_features=20,  # type: int
        samples=1000,  # type: int
        colorize_factors=True,  # type: bool
        alpha=1,  # type: float
        colormap=None,  # type: str
        figsize=(12, 12),  # type: Union[Tuple[float], List[float]]
        jitter=0.35  # type: float
):  # type: (...) -> plt.Figure
    """
    SHAP summary plot

    SHAP summary plot shows contribution of features for each instance. The sum
    of the feature contributions and the bias term is equal to the raw prediction
    of the model, i.e., prediction before applying inverse link function.

    :param model: h2o tree model, such as DRF, XRT, GBM, XGBoost
    :param frame: H2OFrame
    :param columns: either a list of columns or column indices to show. If specified
                    parameter top_n_features will be ignored.
    :param top_n_features: a number of columns to pick using variable importance (where applicable).
    :param samples: maximum number of observations to use; if lower than number of rows in the
                    frame, take a random sample
    :param colorize_factors: if True, use colors from the colormap to colorize the factors;
                             otherwise all levels will have same color
    :param alpha: transparency of the points
    :param colormap: colormap to use instead of the default blue to red colormap
    :param figsize: figure size; passed directly to matplotlib
    :param jitter: amount of jitter used to show the point density
    :return: a matplotlib figure object
    """

    blue_to_red = matplotlib.colors.LinearSegmentedColormap.from_list("blue_to_red",
                                                                      ["#00AAEE", "#FF1166"])

    if colormap is None:
        colormap = blue_to_red
    else:
        colormap = plt.get_cmap(colormap)

    # to prevent problems with data sorted in some logical way
    # (overplotting with latest result which might have different values
    # then the rest of the data in a given region)
    permutation = list(range(frame.nrow))
    random.shuffle(permutation)
    if samples is not None:
        permutation = sorted(permutation[:min(len(permutation), samples)])
        frame = frame[permutation, :]
        permutation = list(range(frame.nrow))
        random.shuffle(permutation)

    with no_progress():
        contributions = NumpyFrame(model.predict_contributions(frame))
    frame = NumpyFrame(frame)
    contribution_names = contributions.columns

    feature_importance = sorted(
        {k: np.abs(v).mean() for k, v in contributions.items() if "BiasTerm" != k}.items(),
        key=lambda kv: kv[1])
    if columns is None:
        top_n = min(top_n_features, len(feature_importance))
        top_n_features = [fi[0] for fi in feature_importance[-top_n:]]
    else:
        picked_cols = []
        columns = [frame.columns[col] if isinstance(col, int) else col for col in columns]
        for feature in columns:
            if feature in contribution_names:
                picked_cols.append(feature)
            else:
                for contrib in contribution_names:
                    if contrib.startswith(feature + "."):
                        picked_cols.append(contrib)
        top_n_features = picked_cols

    plt.figure(figsize=figsize)
    plt.grid(True)
    plt.axvline(0, c="black")

    for i in range(len(top_n_features)):
        col_name = top_n_features[i]
        col = contributions[permutation, col_name]
        dens = _density(col)
        plt.scatter(
            col,
            i + dens * np.random.uniform(-jitter, jitter, size=len(col)),
            alpha=alpha,
            c=_uniformize(frame, col_name)[permutation]
            if colorize_factors or not frame.isfactor(col_name)
            else np.full(frame.nrow, 0.5),
            cmap=colormap
        )
        plt.clim(0, 1)
    cbar = plt.colorbar()
    cbar.set_label('Normalized feature value', rotation=270)
    cbar.ax.get_yaxis().labelpad = 15
    plt.yticks(range(len(top_n_features)), top_n_features)
    plt.xlabel("SHAP value")
    plt.ylabel("Feature")
    plt.title("SHAP Summary plot for \"{}\"".format(model.model_id))
    plt.tight_layout()
    fig = plt.gcf()
    return fig


def shap_explain_row(
        model,  # type: h2o.model.ModelBase
        frame,  # type: h2o.H2OFrame
        row_index,  # type: int
        columns=None,  # type: Optional[Union[List[int], List[str]]]
        top_n_features=10,  # type: int
        figsize=(16, 9),  # type: Union[List[float], Tuple[float]]
        plot_type="barplot",  # type: str
        contribution_type="both"  # type: str
):  # type: (...) -> plt.Figure
    """
    SHAP local explanation

    SHAP explanation shows contribution of features for a given instance. The sum
    of the feature contributions and the bias term is equal to the raw prediction
    of the model, i.e., prediction before applying inverse link function. H2O implements
    TreeSHAP which when the features are correlated, can increase contribution of a feature
    that had no influence on the prediction.

    :param model: h2o tree model, such as DRF, XRT, GBM, XGBoost
    :param frame: H2OFrame
    :param row_index: row index of the instance to inspect
    :param columns: either a list of columns or column indices to show. If specified
                    parameter top_n_features will be ignored.
    :param top_n_features: a number of columns to pick using variable importance (where applicable).
                  When plot_type="barplot", then top_n_features will be chosen for each contribution_type.
    :param figsize: figure size; passed directly to matplotlib
    :param plot_type: either "barplot" or "breakdown"
    :param contribution_type: One of "positive", "negative", or "both".
                              Used only for plot_type="barplot".
    :return: a matplotlib figure object
    """

    row = frame[row_index, :]
    with no_progress():
        contributions = NumpyFrame(model.predict_contributions(row))
    contribution_names = contributions.columns
    prediction = float(contributions.sum(axis=1))
    bias = float(contributions["BiasTerm"])
    contributions = sorted(filter(lambda pair: pair[0] != "BiasTerm", contributions.items()),
                           key=lambda pair: -abs(pair[1]))

    if plot_type == "barplot":
        with no_progress():
            prediction = model.predict(row)[0, "predict"]
        row = NumpyFrame(row)

        if contribution_type == "both":
            contribution_type = ["positive", "negative"]
        else:
            contribution_type = [contribution_type]

        if columns is None:
            picked_features = []
            if "positive" in contribution_type:
                positive_features = sorted(filter(lambda pair: pair[1] >= 0, contributions),
                                           key=lambda pair: pair[1])
                picked_features.extend(positive_features[-min(top_n_features, len(positive_features)):])
            if "negative" in contribution_type:
                negative_features = sorted(filter(lambda pair: pair[1] < 0, contributions),
                                           key=lambda pair: pair[1])
                picked_features.extend(negative_features[:min(top_n_features, len(negative_features))])
        else:
            columns = [frame.columns[col] if isinstance(col, int) else col for col in columns]
            picked_cols = []
            for feature in columns:
                if feature in contribution_names:
                    picked_cols.append(feature)
                else:
                    for contrib in contribution_names:
                        if contrib.startswith(feature + "."):
                            picked_cols.append(contrib)
            picked_features = [pair for pair in contributions if pair[0] in picked_cols]

        picked_features = sorted(picked_features, key=lambda pair: pair[1])

        if len(picked_features) < len(contributions):
            contribution_subset_note = " using {} out of {} contributions".format(
                len(picked_features), len(contributions))
        else:
            contribution_subset_note = ""
        contributions = dict(
            feature=np.array(
                ["{}={}".format(pair[0], str(row.get(pair[0])[0])) for pair in picked_features]),
            value=np.array([pair[1][0] for pair in picked_features])
        )
        plt.figure(figsize=figsize)
        plt.barh(range(contributions["feature"].shape[0]), contributions["value"], fc="#b3ddf2")
        plt.grid(True)
        plt.axvline(0, c="black")
        plt.xlabel("SHAP value")
        plt.ylabel("Feature")
        plt.yticks(range(contributions["feature"].shape[0]), contributions["feature"])
        plt.title("SHAP explanation for {} on row {}{}\nprediction: {}".format(
            model.model_id,
            row_index,
            contribution_subset_note,
            prediction
        ))
        plt.gca().set_axisbelow(True)
        fig = plt.gcf()
        return fig

    elif plot_type == "breakdown":
        if columns is None:
            if top_n_features + 1 < len(contributions):
                contributions = contributions[:top_n_features] + [
                    ("Remaining Features", sum(map(lambda pair: pair[1], contributions[top_n_features:])))]
        else:
            picked_cols = []
            columns = [frame.columns[col] if isinstance(col, int) else col for col in columns]
            for feature in columns:
                if feature in contribution_names:
                    picked_cols.append(feature)
                else:
                    for contrib in contribution_names:
                        if contrib.startswith(feature + "."):
                            picked_cols.append(contrib)
            rest = np.array(sum(pair[1] for pair in contributions if pair[0] not in picked_cols))
            contributions = [pair for pair in contributions if pair[0] in picked_cols]
            if len(contribution_names) - 1 > len(picked_cols):  # Contribution names contain "BiasTerm" as well
                contributions += [("Remaining Features", rest)]

        contributions = contributions[::-1]
        contributions = dict(
            feature=np.array([pair[0] for pair in contributions]),
            value=np.array([pair[1][0] for pair in contributions]),
            color=np.array(["g" if pair[1] >= 0 else "r" for pair in contributions])
        )

        contributions["cummulative_value"] = [bias] + list(
            contributions["value"].cumsum()[:-1] + bias)

        plt.figure(figsize=figsize)
        plt.barh(contributions["feature"], contributions["value"],
                 left=contributions["cummulative_value"],
                 color=contributions["color"])
        plt.axvline(prediction, label="Prediction")
        plt.axvline(bias, linestyle="dotted", color="gray", label="Bias")

        plt.vlines(contributions["cummulative_value"][1:],
                   ymin=[y - 0.4 for y in range(contributions["value"].shape[0])],
                   ymax=[y + 1.4 for y in range(contributions["value"].shape[0])])

        plt.legend()
        plt.grid(True)
        xlim = plt.xlim()
        xlim_diff = xlim[1] - xlim[0]
        plt.xlim((xlim[0] - 0.02 * xlim_diff, xlim[1] + 0.02 * xlim_diff))
        plt.xlabel("SHAP value")
        plt.ylabel("Feature")
        plt.gca().set_axisbelow(True)
        fig = plt.gcf()
        return fig


def _get_top_n_levels(column, top_n):
    # type: (h2o.H2OFrame, int) -> List[str]
    """
    Get top_n levels from factor column based on their frequency.

    :param column: string containing column name
    :param top_n: maximum number of levels to be returned
    :return: list of levels
    """
    counts = column.table().sort("Count", ascending=[False])[:, 0]
    return [
        level[0]
        for level in counts[:min(counts.nrow, top_n), :].as_data_frame(
            use_pandas=False, header=False)
    ]


def _factor_mapper(mapping):
    # type: (Dict) -> Callable
    """
    Helper higher order function returning function that applies mapping to each element.
    :param mapping: dictionary that maps factor names to floats (for NaN; other values are integers)
    :return: function to be applied on iterable
    """

    def _(column):
        return [mapping.get(entry, float("nan")) for entry in column]

    return _


def _add_histogram(frame, column, add_rug=True, add_histogram=True, levels_order=None):
    # type: (H2OFrame, str, bool, bool) -> None
    """
    Helper function to add rug and/or histogram to a plot
    :param frame: H2OFrame
    :param column: string containing column name
    :param add_rug: if True, adds rug
    :param add_histogram: if True, adds histogram
    :return: None
    """
    ylims = plt.ylim()
    nf = NumpyFrame(frame[column])

    if nf.isfactor(column) and levels_order is not None:
        new_mapping = dict(zip(levels_order, range(len(levels_order))))
        mapping = _factor_mapper({k: new_mapping[v] for k, v in nf.from_num_to_factor(column).items()})
    else:
        def mapping(x):
            return x

    if add_rug:
        plt.plot(mapping(nf[column]),
                 [ylims[0] for _ in range(frame.nrow)],
                 "|", color="k", alpha=0.2, ms=20)
    if add_histogram:
        if nf.isfactor(column):
            cnt = Counter(nf[column][np.isfinite(nf[column])])
            hist_x = np.array(list(cnt.keys()), dtype=float)
            hist_y = np.array(list(cnt.values()), dtype=float)
        else:
            hist_y, hist_x = np.histogram(
                mapping(nf[column][np.isfinite(nf[column])]),
                bins=20)
            hist_x = hist_x[:-1].astype(float)
            hist_y = hist_y.astype(float)
        plt.bar(mapping(hist_x),
                hist_y / hist_y.max() * ((ylims[1] - ylims[0]) / 1.618),  # ~ golden ratio
                bottom=ylims[0],
                align="center" if nf.isfactor(column) else "edge",
                width=hist_x[1] - hist_x[0], color="gray", alpha=0.2)
    if nf.isfactor(column):
        plt.xticks(mapping(range(nf.nlevels(column))), nf.levels(column))
    plt.ylim(ylims)


def partial_dependences(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List[h2o.model.model_base]]
        frame,  # type: h2o.H2OFrame
        column,  # type: str
        best_of_family=True,  # type: bool
        row_index=None,  # type: Optional[int]
        target=None,  # type: Optional[str]
        max_factors=30,  # type: int
        figsize=(16, 9),  # type: Union[Tuple[float], List[float]]
        colormap="Dark2",  # type: str
        markers=["o", "v", "s", "P", "*", "D", "X", "^", "<", ">", "."]  # type: List[str]
):  # type: (...) -> plt.Figure
    """
    Plot partial dependences of a variable across multiple models.

    Partial dependence plot (PDP) gives a graphical depiction of the marginal effect of a variable
    on the response. The effect of a variable is measured in change in the mean response.
    PDP assumes independence between the feature for which is the PDP computed and the rest.

    :param models: H2O AutoML object
    :param frame: H2OFrame
    :param column: string containing column name
    :param best_of_family: if True, show only the best models per family
    :param row_index: if None, do partial dependence, if integer, do individual
                      conditional expectation for the row specified by this integer
    :param target: (only for multinomial classification) for what target should the plot be done
    :param max_factors: maximum number of factor levels to show
    :param figsize: figure size; passed directly to matplotlib
    :param colormap: colormap name
    :param markers: List of markers to use for factors, when it runs out of possible markers the last in
                    this list will get reused
    :return: a matplotlib figure object
    """
    if target is not None:
        if isinstance(target, (list, tuple)):
            if len(target) > 1:
                raise ValueError("Only one target can be specified!")
            target = target[0]
        target = [target]
    if isinstance(models, h2o.automl._base.H2OAutoMLBaseMixin):
        all_models = [model_id[0] for model_id in models.leaderboard[:, "model_id"]
            .as_data_frame(use_pandas=False, header=False)]
    else:
        all_models = models

    is_factor = frame[column].isfactor()[0]
    if is_factor:
        if frame[column].nlevels()[0] > max_factors:
            levels = _get_top_n_levels(frame[column], max_factors)
            if row_index is not None:
                levels = list(set(levels + [frame[row_index, column]]))
            frame = frame[(frame[column].isin(levels)), :]
            # decrease the number of levels to the actual number of levels in the subset
            frame[column] = frame[column].ascharacter().asfactor()
    if best_of_family:
        models = _first_of_family(all_models)
    else:
        models = all_models

    models = [m if isinstance(m, h2o.model.ModelBase) else h2o.get_model(m) for m in models]

    colors = plt.get_cmap(colormap, len(models))(list(range(len(models))))
    with no_progress():
        plt.figure(figsize=figsize)
        is_factor = frame[column].isfactor()[0]
        if is_factor:
            factor_map = _factor_mapper(NumpyFrame(frame[column]).from_factor_to_num(column))
            marker_map = dict(zip(range(len(markers) - 1), markers[:-1]))
        model_ids = _shorten_model_ids([model.model_id for model in models])
        for i, model in enumerate(models):
            tmp = NumpyFrame(
                model.partial_plot(frame, cols=[column], plot=False,
                                   row_index=row_index, targets=target,
                                   nbins=20 if not is_factor else 1 + frame[column].nlevels()[0])[0])
            encoded_col = tmp.columns[0]
            if is_factor:
                plt.scatter(factor_map(tmp.get(encoded_col)), tmp["mean_response"],
                            color=[colors[i]], label=model_ids[i],
                            marker=marker_map.get(i, markers[-1]))
            else:
                plt.plot(tmp[encoded_col], tmp["mean_response"], color=colors[i],
                         label=model_ids[i])

        _add_histogram(frame, column)

        if row_index is None:
            plt.title("Partial Dependence plot for \"{}\"{}".format(
                column,
                " with target = \"{}\"".format(target[0]) if target else ""
            ))
        else:
            if is_factor:
                plt.axvline(factor_map([frame[row_index, column]]), c="k", linestyle="dotted",
                            label="Instance value")
            else:
                plt.axvline(frame[row_index, column], c="k", linestyle="dotted",
                            label="Instance value")
            plt.title("Individual Conditional Expectation for column \"{}\" and row {}{}".format(
                column,
                row_index,
                " with target = \"{}\"".format(target[0]) if target else ""
            ))
        ax = plt.gca()
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
        ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        plt.grid(True)
        if is_factor:
            plt.xticks(rotation=45, rotation_mode="anchor", ha="right")
        fig = plt.gcf()
        return fig


def individual_conditional_expectations(
        model,  # type: h2o.model.ModelBase
        frame,  # type: h2o.H2OFrame
        column,  # type: str
        target=None,  # type: Optional[str]
        max_factors=30,  # type: int
        figsize=(16, 9),  # type: Union[Tuple[float], List[float]]
        colormap="plasma",  # type: str
):  # type: (...) -> plt.Figure
    """
    Plot Individual Conditional Expectations (ICE) for each decile

    Individual conditional expectations (ICE) plot gives a graphical depiction of the marginal
    effect of a variable on the response. ICE plot is similar to partial dependence plot (PDP),
    PDP shows the average effect of a feature while ICE plot shows the effect for a single
    instance. The following plot shows the effect for each decile. In contrast to partial
    dependence plot, ICE plot can provide more insight especially when there is stronger feature interaction.

    :param model: H2OModel
    :param frame: H2OFrame
    :param column: string containing column name
    :param target: (only for multinomial classification) for what target should the plot be done
    :param max_factors: maximum number of factor levels to show
    :param figsize: figure size; passed directly to matplotlib
    :param colormap: colormap name
    :return: a matplotlib figure object
    """
    if target is not None:
        if isinstance(target, (list, tuple)):
            if len(target) > 1:
                raise ValueError("Only one target can be specified!")
            target = target[0]
        target = [target]
    with no_progress():
        frame = frame.sort(model.actual_params["response_column"])
        is_factor = frame[column].isfactor()[0]

        if is_factor:
            if frame[column].nlevels()[0] > max_factors:
                levels = _get_top_n_levels(frame[column], max_factors)
                frame = frame[(frame[column].isin(levels)), :]
                # decrease the number of levels to the actual number of levels in the subset
                frame[column] = frame[column].ascharacter().asfactor()

            factor_map = _factor_mapper(NumpyFrame(frame[column]).from_factor_to_num(column))

        deciles = [int(round(frame.nrow * dec / 10)) for dec in range(11)]
        colors = plt.get_cmap(colormap, 11)(list(range(11)))
        plt.figure(figsize=figsize)
        for i, index in enumerate(deciles):
            tmp = NumpyFrame(
                model.partial_plot(
                    frame,
                    cols=[column],
                    plot=False,
                    row_index=index,
                    targets=target,
                    nbins=20 if not is_factor else 1 + frame[column].nlevels()[0]
                )[0]
            )
            encoded_col = tmp.columns[0]
            if is_factor:
                plt.scatter(factor_map(tmp.get(encoded_col)), tmp["mean_response"],
                            color=[colors[i]],
                            label="{}th Percentile".format(i * 10))
            else:
                plt.plot(tmp[encoded_col], tmp["mean_response"], color=colors[i],
                         label="{}th Percentile".format(i * 10))

        tmp = NumpyFrame(
            model.partial_plot(
                frame,
                cols=[column],
                plot=False,
                targets=target,
                nbins=20 if not is_factor else 1 + frame[column].nlevels()[0]
            )[0]
        )
        if is_factor:
            plt.scatter(factor_map(tmp.get(encoded_col)), tmp["mean_response"], color="k",
                        label="Partial Dependence")
        else:
            plt.plot(tmp[encoded_col], tmp["mean_response"], color="k", linestyle="dashed",
                     label="Partial Dependence")

        _add_histogram(frame, column)
        plt.title("Individual Conditional Expectation for \"{}\"\non column \"{}\"{}".format(
            model.model_id,
            column,
            " with target = \"{}\"".format(target[0]) if target else ""
        ))
        ax = plt.gca()
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
        ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        plt.grid(True)
        if is_factor:
            plt.xticks(rotation=45, rotation_mode="anchor", ha="right")
        fig = plt.gcf()
        return fig


def _has_varimp(model):
    # type: (Union[str, h2o.model.ModelBase]) -> bool
    """
    Does model have varimp?
    :param model: model or a string containing model_id
    :return: bool
    """
    return _get_algorithm(model) not in ["stackedensemble", "naivebayes"]


def _get_xy(model):
    # type: (h2o.model.ModelBase) -> Tuple[List[str], str]
    """
    Get features (x) and response column (y).
    :param model: H2O Model
    :return: tuple (x, y)
    """
    y = model.actual_params["response_column"]
    x = [feature for feature in model._model_json["output"]["names"]
         if feature not in y]
    return x, y


def _consolidate_varimps(model):
    # type (h2o.model.ModelBase) -> Dict
    """
    Get variable importances just for the columns that are present in the data set, i.e.,
    when an encoded variables such as "column_name.level_name" are encountered, those variable
    importances are summed to "column_name" variable.

    :param model: H2O Model
    :return: dictionary with variable importances
    """
    x, y = _get_xy(model)

    varimp = {line[0]: line[3] for line in model.varimp()}

    consolidated_varimps = {k: v for k, v in varimp.items() if k in x}
    to_process = {k: v for k, v in varimp.items() if k not in x}

    for feature in to_process.keys():
        col_parts = feature.split(".")
        for i in range(1, len(col_parts) + 1):
            if ".".join(col_parts[:i]) in x:
                column = ".".join(col_parts[:i])
                consolidated_varimps[column] = consolidated_varimps.get(column, 0) + to_process[
                    feature]
                break
        else:
            raise RuntimeError("Cannot find feature {}".format(feature))

    total_value = sum(consolidated_varimps.values())

    if total_value != 1:
        consolidated_varimps = {k: v / total_value for k, v in consolidated_varimps.items()}

    for col in x:
        if col not in consolidated_varimps:
            consolidated_varimps[col] = 0

    return consolidated_varimps


def _interpretable(model):
    # type: (Union[str, h2o.model.ModelBase]) -> bool
    """
    Returns True if model_id is easily interpretable.
    :param model: model or a string containing a model_id
    :return: bool
    """
    return _get_algorithm(model) in ["glm", "gam", "rulefit"]


def _flatten_list(items):
    # type: (list) -> Generator[Any, None, None]
    """
    Flatten nested lists.
    :param items: a list potentionally containing other lists
    :return: flattened list
    """
    for x in items:
        if isinstance(x, list):
            for xx in _flatten_list(x):
                yield xx
        else:
            yield x


def _calculate_clustering_indices(matrix):
    # type: (np.ndarray) -> list
    """
    Get a hierarchical clustering leaves order calculated from the clustering of columns.
    :param matrix: numpy.ndarray
    :return: list of indices of columns
    """
    cols = matrix.shape[1]
    dist = np.zeros((cols, cols))

    for x in range(cols):
        for y in range(cols):
            if x < y:
                dist[x, y] = np.sum(np.power(matrix[:, x] - matrix[:, y], 2))
                dist[y, x] = dist[x, y]
            elif x == y:
                dist[x, x] = float("inf")

    indices = [[i] for i in range(cols)]
    for i in range(cols - 1):
        idx = np.argmin(dist)
        x = idx % cols
        y = idx // cols
        assert x != y
        indices[x].append(indices[y])
        indices[y] = []
        dist[x, :] = np.min(dist[[x, y], :], axis=0)
        dist[y, :] = float("inf")
        dist[:, y] = float("inf")
        dist[x, x] = float("inf")
    result = list(_flatten_list(indices))
    assert len(result) == cols
    return result


def variable_importance_heatmap(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List[h2o.model.ModelBase]]
        top_n=20,  # type: int
        figsize=(16, 9),  # type: Tuple[float]
        cluster=True,  # type: bool
        colormap="RdYlBu_r"  # type: str
):
    # type: (...) -> plt.Figure
    """
    Variable Importance Heatmap across a group of models

    Variable importance heatmap shows variable importances on multiple models.
    By default, the models and variables are ordered by their similarity.

    :param models: H2O AutoML object or list of models
    :param top_n: use just top n models (applies only when used with H2OAutoML)
    :param figsize: figsize: figure size; passed directly to matplotlib
    :param cluster: if True, cluster the models and variables
    :param colormap: colormap to use
    :return: a matplotlib figure object
    """
    if isinstance(models, h2o.automl._base.H2OAutoMLBaseMixin):
        model_ids = [model_id[0] for model_id in models.leaderboard[:, "model_id"]
            .as_data_frame(use_pandas=False, header=False) if _has_varimp(model_id[0])]
        models = [
            h2o.get_model(model_id)
            for model_id in model_ids[:min(top_n, len(model_ids))]
        ]
    else:
        top_n = len(models)
    # Filter out models that don't have varimp
    models = [model for model in models if _has_varimp(model)]
    models = models[:min(len(models), top_n)]
    if len(models) == 0:
        raise RuntimeError("No model with variable importance")

    varimps = [_consolidate_varimps(model) for model in models]

    x, y = _get_xy(models[0])

    varimps = np.array([[varimp[col] for col in x] for varimp in varimps])

    if cluster and len(models) > 2:
        order = _calculate_clustering_indices(varimps)
        x = [x[i] for i in order]
        varimps = varimps[:, order]
        varimps = varimps.transpose()
        order = _calculate_clustering_indices(varimps)
        models = [models[i] for i in order]
        varimps = varimps[:, order]
    else:
        varimps = varimps.transpose()

    plt.figure(figsize=figsize)
    plt.imshow(varimps, cmap=plt.get_cmap(colormap))
    plt.xticks(range(len(models)), _shorten_model_ids([model.model_id for model in models]),
               rotation=45, rotation_mode="anchor", ha="right")
    plt.yticks(range(len(x)), x)
    plt.colorbar()
    plt.xlabel("Model Id")
    plt.ylabel("Feature")
    plt.title("Variable Importance Heatmap")
    plt.grid(False)
    fig = plt.gcf()
    return fig


def model_correlation_heatmap(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List[h2o.model.ModelBase]]
        frame,  # type: h2o.H2OFrame
        top_n=20,  # type: int
        cluster=True,  # type: bool
        triangular=True,  # type: bool
        figsize=(13, 13),  # type: Tuple[float]
        colormap="RdYlBu_r"  # type: str
):
    # type: (...) -> plt.Figure
    """
    Model Prediction Correlation Heatmap

    Model correlation matrix shows correlation between prediction of the models.
    For classification, frequency of same predictions is used. By default, models
    are ordered by their similarity.

    :param models: H2OAutoML object or a list of models
    :param frame: H2OFrame
    :param top_n: show just top n models (applies only when used with H2OAutoML)
    :param cluster: if True, cluster the models
    :param triangular: make the heatmap triangular
    :param figsize: figsize: figure size; passed directly to matplotlib
    :param colormap: colormap to use
    :return: a matplotlib figure object
    """
    if isinstance(models, h2o.automl._base.H2OAutoMLBaseMixin):
        model_ids = [model_id[0] for model_id in models.leaderboard[:, "model_id"]
            .as_data_frame(use_pandas=False, header=False)]
        models = [
            h2o.get_model(model_id)
            for model_id in model_ids[:min(top_n, len(model_ids))]
        ]
    else:
        top_n = len(models)

    is_classification = frame[models[0].actual_params["response_column"]].isfactor()[0]

    models = models[:min(len(models), top_n)]
    predictions = np.empty((len(models), frame.nrow),
                           dtype=np.object if is_classification else np.float)
    with no_progress():
        for idx, model in enumerate(models):
            predictions[idx, :] = np.array(model.predict(frame)["predict"]
                                           .as_data_frame(use_pandas=False, header=False)) \
                .reshape(frame.nrow)

    if is_classification:
        corr = np.zeros((len(models), len(models)))
        for i in range(len(models)):
            for j in range(len(models)):
                if i <= j:
                    corr[i, j] = (predictions[i, :] == predictions[j, :]).mean()
                    corr[j, i] = corr[i, j]
    else:
        corr = np.corrcoef(predictions)

    if cluster:
        order = _calculate_clustering_indices(corr)
        corr = corr[order, :]
        corr = corr[:, order]
        models = [models[i] for i in order]

    if triangular:
        corr = np.where(np.triu(np.ones_like(corr), k=1).astype(bool), float("nan"), corr)

    plt.figure(figsize=figsize)
    plt.imshow(corr, cmap=plt.get_cmap(colormap), clim=(0.5, 1))
    plt.xticks(range(len(models)), _shorten_model_ids([model.model_id for model in models]),
               rotation=45, rotation_mode="anchor", ha="right")
    plt.yticks(range(len(models)), _shorten_model_ids([model.model_id for model in models]))
    plt.colorbar()
    plt.title("Model Correlation")
    plt.xlabel("Model Id")
    plt.ylabel("Model Id")
    plt.grid(False)
    for t in plt.gca().xaxis.get_ticklabels():
        if _interpretable(t.get_text()):
            t.set_color("red")
    for t in plt.gca().yaxis.get_ticklabels():
        if _interpretable(t.get_text()):
            t.set_color("red")
    fig = plt.gcf()
    return fig


def residual_analysis(
        model,  # type: h2o.model.ModelBase
        frame,  # type: h2o.H2OFrame
        figsize=(16, 9)  # type: Tuple[float]
):
    # type: (...) -> plt.Figure
    """
    Residual Analysis

    Do Residual Analysis and creates a plot "Fitted vs Residuals".
    Ideally, residuals should be randomly distributed. Patterns in this plot can indicate
    potential problems with the model selection, e.g., using simpler model than necessary,
    not accounting for heteroscedasticity, autocorrelation, etc.

    :param model: H2OModel
    :param frame: H2OFrame
    :param figsize: figsize: figure size; passed directly to matplotlib
    :return: a matplotlib figure object
    """
    _, y = _get_xy(model)

    with no_progress():
        predicted = NumpyFrame(model.predict(frame)["predict"])
    actual = NumpyFrame(frame[y])

    residuals = predicted["predict"] - actual[y]

    plt.figure(figsize=figsize)
    plt.axhline(y=0, c="k")
    plt.scatter(predicted["predict"], residuals)
    plt.grid(True)
    plt.xlabel("Fitted")
    plt.ylabel("Residuals")
    plt.title("Residual Analysis for \"{}\"".format(model.model_id))

    # Rugs
    xlims = plt.xlim()
    ylims = plt.ylim()
    plt.plot([xlims[0] for _ in range(frame.nrow)], residuals,
             "_", color="k", alpha=0.2, ms=20)
    plt.plot(predicted.get("predict"),
             [ylims[0] for _ in range(frame.nrow)],
             "|", color="k", alpha=0.2, ms=20)

    # Fit line
    X = np.vstack([predicted["predict"], np.ones(frame.nrow)]).T
    slope, const = np.linalg.lstsq(X, residuals, rcond=-1)[0]
    plt.plot(xlims, [xlims[0] * slope + const, xlims[1] * slope + const], c="b")

    plt.xlim(xlims)
    plt.ylim(ylims)

    fig = plt.gcf()
    return fig


def _is_tree_model(model):
    # type: (Union[str, h2o.model.ModelBase]) -> bool
    """
    Is the model a tree model id?
    :param model: model or astring containing a model_id
    :return: bool
    """
    return _get_algorithm(model) in ["drf", "gbm", "xgboost"]


def _get_tree_models(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List[h2o.model.ModelBase]]
        top_n=float("inf")  # type: Union[float, int]
):
    # type: (...) -> List[h2o.model.ModelBase]
    """
    Get list of top_n tree models.

    :param models: either H2OAutoML object or list of H2O Models
    :param top_n: maximum number of tree models to return
    :return: list of tree models
    """
    if isinstance(models, h2o.automl._base.H2OAutoMLBaseMixin):
        model_ids = [model_id[0] for model_id in models.leaderboard[:, "model_id"]
            .as_data_frame(use_pandas=False, header=False)
                     if _is_tree_model(model_id[0])
                     ]
        return [
            h2o.get_model(model_id)
            for model_id in model_ids[:min(top_n, len(model_ids))]
        ]
    elif isinstance(models, h2o.model.ModelBase):
        if _is_tree_model(models):
            return [models]
        else:
            return []
    models = [
        model
        for model in models
        if _is_tree_model(model)
    ]
    return models[:min(len(models), top_n)]


def _get_leaderboard(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List[h2o.model.ModelBase]]
        frame,  # type: h2o.H2OFrame
        row_index=None  # type: Optional[int]
):
    # type: (...) -> h2o.H2OFrame
    """
    Get leaderboard either from AutoML or list of models.

    :param models: H2OAutoML object or list of models
    :param frame: H2OFrame used for calculating prediction when row_index is specified
    :param row_index: if specified, calculated prediction for the given row
    :return: H2OFrame
    """
    if isinstance(models, h2o.automl._base.H2OAutoMLBaseMixin):
        leaderboard = h2o.automl.get_leaderboard(models, extra_columns="ALL")
        if row_index is not None:
            model_ids = [m[0] for m in
                         leaderboard["model_id"].as_data_frame(use_pandas=False, header=False)]
            with no_progress():
                leaderboard = leaderboard.cbind(
                    h2o.H2OFrame.from_python(
                        [h2o.get_model(model_id).predict(frame[row_index, :])[0, "predict"]
                         for model_id in model_ids],
                        column_names=["prediction"]
                    ))
        return leaderboard
    else:
        METRICS = [
            "MSE",
            "RMSE",
            "mae",
            "rmsle",
            "mean_per_class_error",
            "logloss",
        ]
        from collections import defaultdict

        result = defaultdict(list)
        with no_progress():
            for model in models:
                result["model_id"].append(model.model_id)
                perf = model.model_performance(frame)
                for metric in METRICS:
                    result[metric.lower()].append(perf._metric_json.get(metric))
                if row_index is not None:
                    result["prediction"].append(
                        model.predict(frame[row_index, :])[0, "predict"])
            for metric in METRICS:
                if not any(result[metric]):
                    del result[metric]
            leaderboard = h2o.H2OFrame(result)[["model_id"] + [m.lower()
                                                               for m in METRICS + ["prediction"]
                                                               if m.lower() in result]]
            return leaderboard.sort("mse")


def _process_explanation_lists(
        exclude_explanations,  # type: Union[str, List[str]]
        include_explanations,  # type: Union[str, List[str]]
        possible_explanations  # type: List[str]
):
    # type: (...) -> List[str]
    """
    Helper function to process explanation lists.

    :param exclude_explanations: list of model explanations to exclude
    :param include_explanations: list of model explanations to include
    :param possible_explanations: list of all possible explanations
    :return: list of actual explanations
    """
    if not isinstance(include_explanations, list):
        include_explanations = [include_explanations]
    if not isinstance(exclude_explanations, list):
        exclude_explanations = [exclude_explanations]
    include_explanations = [exp.lower() for exp in include_explanations]
    exclude_explanations = [exp.lower() for exp in exclude_explanations]
    if len(exclude_explanations) == 0:
        explanations = possible_explanations if "all" in include_explanations \
            else include_explanations
    else:
        if "all" not in include_explanations:
            raise RuntimeError(
                "Only one of include_explanations or exclude_explanation should be specified!")
        for exp in exclude_explanations:
            if exp not in possible_explanations:
                raise RuntimeError("Unknown explanation \"{}\". Please use one of: {}".format(
                    exp, possible_explanations))
        explanations = [exp for exp in possible_explanations if exp not in exclude_explanations]
    return explanations


def _process_models_input(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List, h2o.model.ModelBase]
        frame,  # type: h2o.H2OFrame
):
    # type: (...) -> Tuple[bool, List, bool, bool, bool, List, List]
    """
    Helper function to get basic information about models/H2OAutoML.

    :param models: H2OAutoML/List of models/H2O Model
    :param frame: H2O Frame
    :return: tuple (is_aml, models_to_show, classification, multinomial_classification,
                    multiple_models, targets, tree_models_to_show)
    """
    is_aml = isinstance(models, h2o.automl._base.H2OAutoMLBaseMixin)
    if is_aml:
        models_to_show = [models.leader]
        multiple_models = models.leaderboard.nrow > 1
    elif isinstance(models, h2o.model.ModelBase):
        models_to_show = [models]
        multiple_models = False
    else:
        models_to_show = models
        multiple_models = len(models) > 1
    tree_models_to_show = _get_tree_models(models, 1 if is_aml else float("inf"))
    y = _get_xy(models_to_show[0])[1]
    classification = frame[y].isfactor()[0]
    multinomial_classification = classification and frame[y].nlevels()[0] > 2
    targets = [None]
    if multinomial_classification:
        targets = [[t] for t in frame[y].levels()[0]]
    return is_aml, models_to_show, classification, multinomial_classification, \
           multiple_models, targets, tree_models_to_show


def _custom_args(user_specified, **kwargs):
    # type: (Optional[Dict], **Any) -> Dict
    """
    Helper function to make customization of arguments easier.

    :param user_specified: dictionary of user specified overrides or None
    :param kwargs: default values, such as, `top_n=5`
    :return: dictionary of actual arguments to use
    """
    if user_specified is None:
        user_specified = dict()

    result = dict(**kwargs)
    result.update(user_specified)

    return result


def explain(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List[h2o.model.ModelBase]]
        frame,  # type: h2o.H2OFrame
        columns=None,  # type: Optional[Union[List[int], List[str]]]
        top_n_features=5,  # type: int
        include_explanations="ALL",  # type: Union[str, List[str]]
        exclude_explanations=[],  # type: Union[str, List[str]]
        plot_overrides=dict(),  # type: Dict
        figsize=(16, 9),  # type: Tuple[float]
        render=True,  # type: bool
        qualitative_colormap="Dark2",  # type: str
        sequential_colormap="RdYlBu_r"  # type: str
):
    # type: (...) -> H2OExplanation
    """
    Generate model explanations on frame data set.

    :param models: H2OAutoML object or H2OModel
    :param frame: H2OFrame
    :param columns: either a list of columns or column indices to show. If specified
                    parameter top_n_features will be ignored.
    :param top_n_features: a number of columns to pick using variable importance (where applicable).
    :param include_explanations: if specified, return only the specified model explanations
                                 (Mutually exclusive with exclude_explanations)
    :param exclude_explanations: exclude specified model explanations
    :param plot_overrides: overrides for individual model explanations
    :param figsize: figure size; passed directly to matplotlib
    :param render: if True, render the model explanations; otherwise model explanations are just returned
    :return: H2OExplanation containing the model explanations including headers and descriptions
    """
    is_aml, models_to_show, classification, multinomial_classification, multiple_models, \
    targets, tree_models_to_show = _process_models_input(models, frame)

    if columns is not None and isinstance(columns, list):
        columns_of_interest = [frame.columns[col] if isinstance(col, int) else col for col in columns]
    else:
        columns_of_interest = None

    models_with_varimp = [model for model in models_to_show if _has_varimp(model)]

    if len(models_with_varimp) == 0 and is_aml:
        models_with_varimp = [model_id[0] for model_id in models.leaderboard["model_id"]
            .as_data_frame(use_pandas=False, header=False) if _has_varimp(model_id[0])]
        models_with_varimp = [h2o.get_model(models_with_varimp[0])]

    possible_explanations = [
        "leaderboard",
        "confusion_matrix",
        "residual_analysis",
        "variable_importance",
        "variable_importance_heatmap",
        "model_correlation_heatmap",
        "shap_summary",
        "pdp",
        "ice"
    ]

    explanations = _process_explanation_lists(
        exclude_explanations=exclude_explanations,
        include_explanations=include_explanations,
        possible_explanations=possible_explanations
    )

    if render:
        display = _display
    else:
        display = _dont_display

    result = H2OExplanation()
    if multiple_models and "leaderboard" in explanations:
        result["leaderboard"] = H2OExplanation()
        result["leaderboard"]["header"] = display(Header("Leaderboard"))
        result["leaderboard"]["description"] = display(Description("leaderboard"))
        result["leaderboard"]["data"] = display(_get_leaderboard(models, frame))

    if classification:
        if "confusion_matrix" in explanations:
            result["confusion_matrix"] = H2OExplanation()
            result["confusion_matrix"]["header"] = display(Header("Confusion Matrix"))
            result["confusion_matrix"]["description"] = display(Description("confusion_matrix"))
            result["confusion_matrix"]["subexplanations"] = H2OExplanation()
            for model in models_to_show:
                result["confusion_matrix"]["subexplanations"][model.model_id] = H2OExplanation()
                result["confusion_matrix"]["subexplanations"][model.model_id]["header"] = display(
                    Header(model.model_id, 2))
                result["confusion_matrix"]["subexplanations"][model.model_id]["plots"] = H2OExplanation()
                if multinomial_classification:
                    result["confusion_matrix"]["subexplanations"][model.model_id]["plots"][model.model_id] = display(
                        model.confusion_matrix(
                            **_custom_args(plot_overrides.get("confusion_matrix"),
                                           data=frame)))
                else:
                    result["confusion_matrix"]["subexplanations"][model.model_id]["plots"][model.model_id] = display(
                        model.confusion_matrix())
    else:
        if "residual_analysis" in explanations:
            result["residual_analysis"] = H2OExplanation()
            result["residual_analysis"]["header"] = display(Header("Residual Analysis"))
            result["residual_analysis"]["description"] = display(Description("residual_analysis"))
            result["residual_analysis"]["plots"] = H2OExplanation()
            for model in models_to_show:
                result["residual_analysis"]["plots"][model.model_id] = display(
                    residual_analysis(model,
                                      frame,
                                      **_custom_args(
                                          plot_overrides.get(
                                              "residual_analysis"),
                                          figsize=figsize)))

    if len(models_with_varimp) > 0 and "variable_importance" in explanations:
        result["variable_importance"] = H2OExplanation()
        result["variable_importance"]["header"] = display(Header("Variable Importance"))
        result["variable_importance"]["description"] = display(Description("variable_importance"))
        result["variable_importance"]["plots"] = H2OExplanation()
        for model in models_with_varimp:
            model.varimp_plot(server=True, **plot_overrides.get("varimp_plot", dict()))
            varimp_plot = plt.gcf()  # type: plt.Figure
            varimp_plot.set_figwidth(figsize[0])
            varimp_plot.set_figheight(figsize[1])
            varimp_plot.gca().set_title("Variable Importance for \"{}\"".format(model.model_id))
            result["variable_importance"]["plots"][model.model_id] = display(varimp_plot)
        if columns_of_interest is None:
            varimps = _consolidate_varimps(models_with_varimp[0])
            columns_of_interest = sorted(varimps.keys(), key=lambda k: -varimps[k])[
                                  :min(top_n_features, len(varimps))]
    else:
        if columns_of_interest is None:
            columns_of_interest = _get_xy(models_to_show[0])[0]

    if is_aml or len(models_to_show) > 1:
        if "variable_importance_heatmap" in explanations:
            result["variable_importance_heatmap"] = H2OExplanation()
            result["variable_importance_heatmap"]["header"] = display(
                Header("Variable Importance Heatmap"))
            result["variable_importance_heatmap"]["description"] = display(
                Description("variable_importance_heatmap"))
            result["variable_importance_heatmap"]["plots"] = display(variable_importance_heatmap(
                models,
                **_custom_args(plot_overrides.get("variable_importance_heatmap"),
                               colormap=sequential_colormap,
                               figsize=figsize)))

        if "model_correlation_heatmap" in explanations:
            result["model_correlation_heatmap"] = H2OExplanation()
            result["model_correlation_heatmap"]["header"] = display(Header("Model Correlation"))
            result["model_correlation_heatmap"]["description"] = display(Description(
                "model_correlation_heatmap"))
            result["model_correlation_heatmap"]["plots"] = display(model_correlation_heatmap(
                models, **_custom_args(plot_overrides.get("model_correlation_heatmap"),
                                       frame=frame,
                                       colormap=sequential_colormap,
                                       figsize=figsize)))

    # SHAP Summary
    if len(tree_models_to_show) > 0 and not multinomial_classification \
            and "shap_summary" in explanations:
        result["shap_summary"] = H2OExplanation()
        result["shap_summary"]["header"] = display(Header("SHAP Summary"))
        result["shap_summary"]["description"] = display(Description("shap_summary"))
        result["shap_summary"]["plots"] = H2OExplanation()
        for tree_model in tree_models_to_show:
            result["shap_summary"]["plots"][tree_model.model_id] = display(shap_summary_plot(
                tree_model,
                **_custom_args(
                    plot_overrides.get("shap_summary_plot"),
                    frame=frame,
                    figsize=figsize
                )))

    # PDP
    if "pdp" in explanations:
        if is_aml or multiple_models:
            result["pdp"] = H2OExplanation()
            result["pdp"]["header"] = display(Header("Partial Dependence Plots"))
            result["pdp"]["description"] = display(Description("pdp"))
            result["pdp"]["plots"] = H2OExplanation()
            for column in columns_of_interest:
                result["pdp"]["plots"][column] = H2OExplanation()
                for target in targets:
                    pdp = display(partial_dependences(
                        models, column=column, target=target,
                        **_custom_args(plot_overrides.get("partial_dependences"),
                                       frame=frame,
                                       figsize=figsize,
                                       colormap=qualitative_colormap)))
                    if target is None:
                        result["pdp"]["plots"][column] = pdp
                    else:
                        result["pdp"]["plots"][column][target[0]] = pdp
        else:
            result["pdp"] = H2OExplanation()
            result["pdp"]["header"] = display(Header("Partial Dependence Plots"))
            result["pdp"]["description"] = display(Description("pdp"))
            result["pdp"]["plots"] = H2OExplanation()
            for column in columns_of_interest:
                result["pdp"]["plots"][column] = H2OExplanation()
                for target in targets:
                    reduced_frame = frame
                    is_factor = reduced_frame[column].isfactor()[0]
                    if is_factor:
                        reduced_frame = reduced_frame[
                                        reduced_frame[column].isin(_get_top_n_levels(reduced_frame[column], 30)), :]
                        reduced_frame[column] = reduced_frame[column].ascharacter().asfactor()
                    with no_progress():
                        models_to_show[0].partial_plot(cols=[column], server=True,
                                                       targets=target,
                                                       **_custom_args(
                                                           plot_overrides.get("partial_plot"),
                                                           data=reduced_frame,
                                                           figsize=figsize,
                                                           nbins=20 if not is_factor
                                                           else 1 + reduced_frame[column].nlevels()[0]))
                    fig = plt.gcf()  # type: plt.Figure
                    _add_histogram(reduced_frame, column,
                                   levels_order=[t.get_text() for t in fig.gca().get_xticklabels()])
                    if is_factor:
                        plt.xticks(rotation=45, rotation_mode="anchor", ha="right")
                    if target is None:
                        result["pdp"]["plots"][column] = display(fig)
                    else:
                        result["pdp"]["plots"][column][target[0]] = display(fig)

    # ICE
    if "ice" in explanations and not classification:
        result["ice"] = H2OExplanation()
        result["ice"]["header"] = display(Header("Individual Conditional Expectation"))
        result["ice"]["description"] = display(Description("ice"))
        result["ice"]["plots"] = H2OExplanation()
        for column in columns_of_interest:
            result["ice"]["plots"][columns] = H2OExplanation()
            for model in models_to_show:
                result["ice"]["plots"][columns][model] = H2OExplanation()
                for target in targets:
                    ice = display(
                        individual_conditional_expectations(
                            model, column=column,
                            target=target,
                            **_custom_args(
                                plot_overrides.get("individual_conditional_expectations"),
                                frame=frame,
                                figsize=figsize,
                                colormap=sequential_colormap
                            )))
                    if target is None:
                        result["ice"]["plots"][columns][model] = ice
                    else:
                        result["ice"]["plots"][columns][model][target[0]] = ice

    return result


def explain_row(
        models,  # type: Union[h2o.automl._base.H2OAutoMLBaseMixin, List[h2o.model.ModelBase]]
        frame,  # type: h2o.H2OFrame
        row_index,  # type: int
        columns=None,  # type: Optional[Union[List[int], List[str]]]
        top_n_features=5,  # type: int
        include_explanations="ALL",  # type: Union[str, List[str]]
        exclude_explanations=[],  # type: Union[str, List[str]]
        plot_overrides=dict(),  # type: Dict
        qualitative_colormap="Dark2",  # type: str
        figsize=(16, 9),  # type: Tuple[float]
        render=True,  # type: bool
):
    # type: (...) -> H2OExplanation
    """
    Generate model explanations on frame data set for a given instance.

    :param models: H2OAutoML object or H2OModel
    :param frame: H2OFrame
    :param row_index: row index of the instance to inspect
    :param columns: either a list of columns or column indices to show. If specified
                    parameter top_n_features will be ignored.
    :param top_n_features: a number of columns to pick using variable importance (where applicable).
    :param include_explanations: if specified, return only the specified model explanations
                                 (Mutually exclusive with exclude_explanations)
    :param exclude_explanations: exclude specified model explanations
    :param plot_overrides: overrides for individual model explanations
    :param qualitative_colormap: a colormap name
    :param figsize: figure size; passed directly to matplotlib
    :param render: if True, render the model explanations; otherwise model explanations are just returned

    :return: H2OExplanation containing the model explanations including headers and descriptions
    """
    is_aml, models_to_show, _, multinomial_classification, multiple_models, \
    targets, tree_models_to_show = _process_models_input(models, frame)

    models_with_varimp = [model for model in models_to_show if _has_varimp(model)]

    if len(models_with_varimp) == 0 and is_aml:
        models_with_varimp = [model_id[0] for model_id in models.leaderboard["model_id"]
            .as_data_frame(use_pandas=False, header=False) if _has_varimp(model_id[0])]
        models_with_varimp = [h2o.get_model(models_with_varimp[0])]

    if columns is not None and isinstance(columns, list):
        columns_of_interest = [frame.columns[col] if isinstance(col, int) else col for col in columns]
    else:
        if len(models_with_varimp) > 0:
            varimps = _consolidate_varimps(models_with_varimp[0])
            columns_of_interest = sorted(varimps.keys(), key=lambda k: -varimps[k])[
                                  :min(top_n_features, len(varimps))]
        else:
            import warnings
            warnings.warn("No model with variable importance. Selecting all features to explain.")
            columns_of_interest = _get_xy(models_to_show[0])[0]

    possible_explanations = ["leaderboard", "shap_explain_row", "ice"]

    explanations = _process_explanation_lists(
        exclude_explanations=exclude_explanations,
        include_explanations=include_explanations,
        possible_explanations=possible_explanations
    )

    if render:
        display = _display
    else:
        display = _dont_display

    result = H2OExplanation()
    if multiple_models and "leaderboard" in explanations:
        result["leaderboard"] = H2OExplanation()
        result["leaderboard"]["header"] = display(Header("Leaderboard"))
        result["leaderboard"]["description"] = display(Description("leaderboard_row"))
        result["leaderboard"]["data"] = display(_get_leaderboard(models, row_index=row_index,
                                                         **_custom_args(
                                                             plot_overrides.get("leaderboard"),
                                                             frame=frame)))

    if len(tree_models_to_show) > 0 and not multinomial_classification and \
            "shap_explain_row" in explanations:
        result["shap_explain_row"] = H2OExplanation()
        result["shap_explain_row"]["header"] = display(Header("SHAP Explanation"))
        result["shap_explain_row"]["description"] = display(Description("shap_explain_row"))
        for tree_model in tree_models_to_show:
            result["shap_explain_row"][tree_model.model_id] = display(shap_explain_row(
                tree_model, row_index=row_index,
                **_custom_args(plot_overrides.get("shap_explain_row"),
                               frame=frame, figsize=figsize)))

    if "ice" in explanations:
        result["ice"] = H2OExplanation()
        result["ice"]["header"] = display(Header("Individual Conditional Expectation"))
        result["ice"]["description"] = display(Description("ice_row"))
        result["ice"]["plots"] = H2OExplanation()
        for column in columns_of_interest:
            result["ice"]["plots"][column] = H2OExplanation()
            for target in targets:
                if multiple_models:
                    ice = display(partial_dependences(
                        models, column=column,
                        row_index=row_index,
                        target=target,
                        **_custom_args(
                            plot_overrides.get("individual_conditional_expectations",
                                               plot_overrides.get("partial_dependences")),
                            frame=frame,
                            best_of_family=is_aml,
                            figsize=figsize,
                            colormap=qualitative_colormap
                        )))
                    if target is None:
                        result["ice"]["plots"][column] = ice
                    else:
                        result["ice"]["plots"][column][target[0]] = ice
                else:
                    reduced_frame = frame
                    is_factor = reduced_frame[column].isfactor()[0]
                    if is_factor:
                        reduced_frame = reduced_frame[
                                        reduced_frame[column].isin(_get_top_n_levels(reduced_frame[column], 30)), :]
                        reduced_frame[column] = reduced_frame[column].ascharacter().asfactor()
                    with no_progress():
                        models_to_show[0].partial_plot(
                            cols=[column], server=True,
                            row_index=row_index, targets=target,
                            **_custom_args(
                                plot_overrides.get("individual_conditional_expectations",
                                                   plot_overrides.get("partial_dependences")),
                                data=reduced_frame, figsize=figsize,
                                nbins=20 if not is_factor
                                else 1 + reduced_frame[column].nlevels()[0]))
                    fig = plt.gcf()  # type: plt.Figure
                    fig.gca().set_title("Individual Conditional Expectation for \"{}\" and row index {}".format(
                        column,
                        row_index
                    ))
                    _add_histogram(reduced_frame, column,
                                   levels_order=[t.get_text() for t in fig.gca().get_xticklabels()])
                    if is_factor:
                        plt.xticks(rotation=45, rotation_mode="anchor", ha="right")
                    if target is None:
                        result["ice"]["plots"][column] = display(fig)
                    else:
                        result["ice"]["plots"][column][target[0]] = display(fig)

    return result
