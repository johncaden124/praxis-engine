"""Reference solution for c4_numpy."""
import numpy as np

from station_api import submit_result, test_inputs, training_data

X, y = map(np.array, training_data())
mu, sd = X.mean(0), X.std(0)
Xn = (X - mu) / sd
w, b = np.zeros(2), 0.0
for _ in range(3000):
    err = Xn @ w + b - y
    w -= 0.05 * 2 * Xn.T @ err / len(y)
    b -= 0.05 * 2 * err.mean()
pred = ((np.array(test_inputs()) - mu) / sd) @ w + b
submit_result(predictions=pred.tolist())
