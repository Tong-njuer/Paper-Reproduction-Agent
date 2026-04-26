LiteMLM: A Minimal Reproduction Benchmark for Multi-Label Classification

Abstract
We introduce LiteMLM, a lightweight benchmark for multi-label reproduction tasks.
The objective is to validate tooling with a deterministic workflow rather than SOTA accuracy.

Method
We train a simple linear model and evaluate thresholded outputs.
Reference implementation is published at https://github.com/example/litemlm.
A related preprint appears at https://arxiv.org/abs/2401.12345.

Datasets
We use CIFAR-10 and MNIST style toy splits for pipeline validation.

Metrics
Primary metrics are accuracy, f1, precision, and recall.

Code Snippet
```python
import numpy as np

class LiteMLM:
    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.weights = None

    def fit(self, x: np.ndarray, y: np.ndarray):
        x_bias = np.concatenate([x, np.ones((x.shape[0], 1))], axis=1)
        self.weights = np.linalg.pinv(x_bias) @ y
        return self

    def predict(self, x: np.ndarray):
        x_bias = np.concatenate([x, np.ones((x.shape[0], 1))], axis=1)
        scores = x_bias @ self.weights
        return (scores >= self.threshold).astype(int)
```

Experiments
The benchmark runs under CPU in less than one minute.
