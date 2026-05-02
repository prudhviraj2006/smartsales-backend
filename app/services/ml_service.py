"""
ML Service – Prophet and LightGBM model training, evaluation, and forecasting.
"""
import pandas as pd
import numpy as np
from datetime import timedelta
from typing import Dict, Any, Tuple, Optional
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def calculate_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculate Mean Absolute Percentage Error."""
    mask = y_true != 0
    if mask.sum() == 0:
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def prepare_time_series(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    aggregation: str = "daily"
) -> pd.DataFrame:
    """Prepare and aggregate time series data."""
    data = df[[date_col, target_col]].copy()
    data[date_col] = pd.to_datetime(data[date_col])
    data = data.sort_values(date_col).reset_index(drop=True)

    if aggregation == "weekly":
        data = data.set_index(date_col).resample("W").sum().reset_index()
    elif aggregation == "monthly":
        data = data.set_index(date_col).resample("M").sum().reset_index()

    data.columns = ["ds", "y"]
    return data


def train_prophet(
    df: pd.DataFrame,
    horizon_months: int = 6,
    test_ratio: float = 0.2
) -> Dict[str, Any]:
    """Train Prophet model and generate forecasts."""
    from prophet import Prophet

    # Train/test split
    split_idx = int(len(df) * (1 - test_ratio))
    train = df.iloc[:split_idx].copy()
    test = df.iloc[split_idx:].copy()

    # Train model
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
    )
    model.fit(train)

    # Predict on test set
    test_forecast = model.predict(test[["ds"]])

    # Evaluate
    y_true = test["y"].values
    y_pred = test_forecast["yhat"].values
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = calculate_mape(y_true, y_pred)
    r2 = float(r2_score(y_true, y_pred))
    residuals = (y_true - y_pred).tolist()
    mean_error = float(np.mean(residuals))
    std_error = float(np.std(residuals))

    # Generate future forecast
    last_date = df["ds"].max()
    future_periods = horizon_months * 30  # approx days
    future = model.make_future_dataframe(periods=future_periods, freq="D")
    forecast = model.predict(future)

    # Only future dates
    future_forecast = forecast[forecast["ds"] > last_date]

    forecast_data = []
    for _, row in future_forecast.iterrows():
        forecast_data.append({
            "date": row["ds"].strftime("%Y-%m-%d"),
            "value": round(float(row["yhat"]), 2),
        })

    confidence_lower = [
        {
            "date": row["ds"].strftime("%Y-%m-%d"),
            "value": round(float(row["yhat_lower"]), 2),
        }
        for _, row in future_forecast.iterrows()
    ]
    confidence_upper = [
        {
            "date": row["ds"].strftime("%Y-%m-%d"),
            "value": round(float(row["yhat_upper"]), 2),
        }
        for _, row in future_forecast.iterrows()
    ]

    actual_data = [
        {"date": row["ds"].strftime("%Y-%m-%d"), "value": round(float(row["y"]), 2)}
        for _, row in df.iterrows()
    ]

    # Calculate projected revenue & growth
    recent_avg = float(df["y"].tail(30).mean()) if len(df) >= 30 else float(df["y"].mean())
    forecast_avg = float(future_forecast["yhat"].mean())
    projected_revenue = round(forecast_avg * horizon_months * 30, 2)
    growth_rate = round(
        ((forecast_avg - recent_avg) / recent_avg * 100) if recent_avg != 0 else 0, 2
    )
    accuracy = round(100 - mape, 2)

    # Determine top driver
    components = model.predict(df[["ds"]])
    trend_strength = float(components["trend"].std())
    seasonality_cols = [c for c in components.columns if "yearly" in c or "weekly" in c]
    seasonality_strength = sum(
        float(components[c].std()) for c in seasonality_cols
    )

    top_driver = "Trend" if trend_strength > seasonality_strength else "Seasonality"

    # Time Series Decomposition (Prophet only)
    components_df = model.predict(df[["ds"]])
    decomposition = {
        "trend": [
            {"date": row["ds"].strftime("%Y-%m-%d"), "value": round(float(row["trend"]), 2)}
            for _, row in components_df.iterrows()
        ],
        "seasonal": [
            {"date": row["ds"].strftime("%Y-%m-%d"), "value": round(float(row["yearly"] if "yearly" in row else (row["weekly"] if "weekly" in row else 0)), 2)}
            for _, row in components_df.iterrows()
        ],
        "residual": [
            {"date": row["ds"].strftime("%Y-%m-%d"), "value": round(float(row["y"] - row["yhat"]), 2)}
            for _, (idx, row) in pd.concat([df.reset_index(drop=True), components_df.reset_index(drop=True)], axis=1).iterrows()
        ]
    }

    return {
        "model_type": "prophet",
        "forecast_data": forecast_data,
        "actual_data": actual_data,
        "confidence_lower": confidence_lower,
        "confidence_upper": confidence_upper,
        "projected_revenue": projected_revenue,
        "growth_rate": growth_rate,
        "accuracy": accuracy,
        "top_driver": top_driver,
        "decomposition": decomposition,
        "metrics": {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 4),
            "r2_score": round(r2, 4),
            "mean_error": round(mean_error, 4),
            "std_error": round(std_error, 4),
            "residuals": [round(r, 4) for r in residuals],
        },
    }


def create_lgbm_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create lag and rolling features for LightGBM."""
    data = df.copy()
    data["month"] = data["ds"].dt.month
    data["quarter"] = data["ds"].dt.quarter
    data["day_of_week"] = data["ds"].dt.dayofweek
    data["day_of_year"] = data["ds"].dt.dayofyear
    data["week_of_year"] = data["ds"].dt.isocalendar().week.astype(int)

    # Lag features
    for lag in [1, 7, 14, 30]:
        data[f"lag_{lag}"] = data["y"].shift(lag)

    # Rolling averages
    for window in [7, 14, 30]:
        data[f"rolling_mean_{window}"] = data["y"].rolling(window=window).mean()
        data[f"rolling_std_{window}"] = data["y"].rolling(window=window).std()

    data = data.dropna().reset_index(drop=True)
    return data


def train_lightgbm(
    df: pd.DataFrame,
    horizon_months: int = 6,
    test_ratio: float = 0.2
) -> Dict[str, Any]:
    """Train LightGBM model and generate forecasts."""
    import lightgbm as lgb

    data = create_lgbm_features(df)

    feature_cols = [
        c for c in data.columns if c not in ["ds", "y"]
    ]

    # Train/test split
    split_idx = int(len(data) * (1 - test_ratio))
    train = data.iloc[:split_idx]
    test = data.iloc[split_idx:]

    X_train = train[feature_cols]
    y_train = train["y"]
    X_test = test[feature_cols]
    y_test = test["y"]

    # Train model
    model = lgb.LGBMRegressor(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=7,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_test, y_test)],
    )

    # Evaluate
    y_pred = model.predict(X_test)
    mae = float(mean_absolute_error(y_test.values, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test.values, y_pred)))
    mape = calculate_mape(y_test.values, y_pred)
    r2 = float(r2_score(y_test.values, y_pred))
    residuals = (y_test.values - y_pred).tolist()
    mean_error = float(np.mean(residuals))
    std_error = float(np.std(residuals))

    # Future forecast (iterative)
    future_periods = horizon_months * 30
    last_known = data.iloc[-1:].copy()
    forecast_data = []

    current_data = data.copy()
    for i in range(future_periods):
        last_date = current_data["ds"].max()
        next_date = last_date + timedelta(days=1)
        next_row = pd.DataFrame({"ds": [next_date], "y": [np.nan]})
        temp = pd.concat([current_data, next_row], ignore_index=True)

        # Recompute features
        temp["month"] = temp["ds"].dt.month
        temp["quarter"] = temp["ds"].dt.quarter
        temp["day_of_week"] = temp["ds"].dt.dayofweek
        temp["day_of_year"] = temp["ds"].dt.dayofyear
        temp["week_of_year"] = temp["ds"].dt.isocalendar().week.astype(int)

        for lag_val in [1, 7, 14, 30]:
            temp[f"lag_{lag_val}"] = temp["y"].shift(lag_val)
        for window in [7, 14, 30]:
            temp[f"rolling_mean_{window}"] = temp["y"].rolling(window=window).mean()
            temp[f"rolling_std_{window}"] = temp["y"].rolling(window=window).std()

        last_row = temp.iloc[-1:]
        X_pred = last_row[feature_cols].fillna(0)
        pred_val = float(model.predict(X_pred)[0])

        temp.iloc[-1, temp.columns.get_loc("y")] = pred_val
        current_data = temp.copy()

        forecast_data.append({
            "date": next_date.strftime("%Y-%m-%d"),
            "value": round(pred_val, 2),
        })

    actual_data = [
        {"date": row["ds"].strftime("%Y-%m-%d"), "value": round(float(row["y"]), 2)}
        for _, row in df.iterrows()
    ]

    # Confidence intervals (±1.5 std)
    pred_std = std_error * 1.5
    confidence_lower = [
        {"date": f["date"], "value": round(f["value"] - pred_std, 2)}
        for f in forecast_data
    ]
    confidence_upper = [
        {"date": f["date"], "value": round(f["value"] + pred_std, 2)}
        for f in forecast_data
    ]

    # Calculate projected revenue & growth
    recent_avg = float(df["y"].tail(30).mean()) if len(df) >= 30 else float(df["y"].mean())
    forecast_vals = [f["value"] for f in forecast_data]
    forecast_avg = float(np.mean(forecast_vals))
    projected_revenue = round(forecast_avg * horizon_months * 30, 2)
    growth_rate = round(
        ((forecast_avg - recent_avg) / recent_avg * 100) if recent_avg != 0 else 0, 2
    )
    accuracy = round(100 - mape, 2)

    # Feature importance for top driver
    importances = dict(zip(feature_cols, model.feature_importances_))
    top_driver = max(importances, key=importances.get)

    return {
        "model_type": "lightgbm",
        "forecast_data": forecast_data,
        "actual_data": actual_data,
        "confidence_lower": confidence_lower,
        "confidence_upper": confidence_upper,
        "projected_revenue": projected_revenue,
        "growth_rate": growth_rate,
        "accuracy": accuracy,
        "top_driver": top_driver,
        "metrics": {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 4),
            "r2_score": round(r2, 4),
            "mean_error": round(mean_error, 4),
            "std_error": round(std_error, 4),
            "residuals": [round(r, 4) for r in residuals],
        },
    }


def train_model(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    model_type: str = "lightgbm",
    aggregation: str = "daily",
    horizon_months: int = 6,
) -> Dict[str, Any]:
    """Main entry point: prepare data and train the selected model."""
    ts_data = prepare_time_series(df, date_col, target_col, aggregation)

    if len(ts_data) < 30:
        raise ValueError("Need at least 30 data points for forecasting.")

    if model_type == "prophet":
        return train_prophet(ts_data, horizon_months)
    elif model_type == "lightgbm":
        return train_lightgbm(ts_data, horizon_months)
    else:
        raise ValueError(f"Unsupported model type: {model_type}")
