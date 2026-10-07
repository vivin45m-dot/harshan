"""Networks: one GRU encoder, three heads.

* EvidentialNet - outputs (gamma, nu, alpha, beta) of a Normal-Inverse-Gamma
  distribution (Amini et al., 2020).
* GaussianNet - mean and variance; used with dropout left on at test time
  for the MC-dropout baseline.
* PointNet - plain regression, same encoder, for the "no uncertainty" baseline.

The encoder deliberately has no node-ID embedding. If it did, every node
would look "familiar" and epistemic uncertainty would lose its meaning.
"""
import math

import torch
from torch import nn
import torch.nn.functional as F


class Encoder(nn.Module):
    def __init__(self, n_seq, n_static, hidden=64, dropout=0.1):
        super().__init__()
        self.gru = nn.GRU(n_seq, hidden, num_layers=2, batch_first=True, dropout=dropout)
        self.mix = nn.Sequential(
            nn.Linear(hidden + n_static, hidden), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(dropout),
        )

    def forward(self, x_seq, x_static):
        _, h = self.gru(x_seq)
        return self.mix(torch.cat([h[-1], x_static], dim=-1))


class EvidentialNet(nn.Module):
    def __init__(self, n_seq, n_static, hidden=64, dropout=0.1):
        super().__init__()
        self.encoder = Encoder(n_seq, n_static, hidden, dropout)
        self.head = nn.Linear(hidden, 4)

    def forward(self, x_seq, x_static):
        out = self.head(self.encoder(x_seq, x_static))
        gamma, lognu, logalpha, logbeta = out.unbind(-1)
        nu = F.softplus(lognu) + 1e-6
        alpha = F.softplus(logalpha) + 1.0 + 1e-6
        beta = F.softplus(logbeta) + 1e-6
        return gamma, nu, alpha, beta


class GaussianNet(nn.Module):
    def __init__(self, n_seq, n_static, hidden=64, dropout=0.2):
        super().__init__()
        self.encoder = Encoder(n_seq, n_static, hidden, dropout)
        self.head = nn.Linear(hidden, 2)

    def forward(self, x_seq, x_static):
        mean, raw_var = self.head(self.encoder(x_seq, x_static)).unbind(-1)
        return mean, F.softplus(raw_var) + 1e-6


class PointNet(nn.Module):
    def __init__(self, n_seq, n_static, hidden=64, dropout=0.1):
        super().__init__()
        self.encoder = Encoder(n_seq, n_static, hidden, dropout)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x_seq, x_static):
        return self.head(self.encoder(x_seq, x_static)).squeeze(-1)


# --- losses ------------------------------------------------------------------

def nig_nll(y, gamma, nu, alpha, beta):
    """Negative log-likelihood of y under the NIG marginal (a Student-t)."""
    omega = 2.0 * beta * (1.0 + nu)
    return (0.5 * torch.log(math.pi / nu)
            - alpha * torch.log(omega)
            + (alpha + 0.5) * torch.log(nu * (y - gamma) ** 2 + omega)
            + torch.lgamma(alpha) - torch.lgamma(alpha + 0.5))


def nig_regulariser(y, gamma, nu, alpha):
    # Evidence (2nu + alpha) is penalised in proportion to the error, so the
    # model cannot claim lots of evidence for a prediction that is wrong.
    return torch.abs(y - gamma) * (2.0 * nu + alpha)


def evidential_loss(y, gamma, nu, alpha, beta, lam):
    return (nig_nll(y, gamma, nu, alpha, beta) + lam * nig_regulariser(y, gamma, nu, alpha)).mean()


def gaussian_nll(y, mean, var):
    return (0.5 * (torch.log(2 * math.pi * var) + (y - mean) ** 2 / var)).mean()


# --- uncertainty read-outs ---------------------------------------------------

def nig_moments(gamma, nu, alpha, beta):
    """Prediction, aleatoric E[sigma^2], epistemic Var[mu]."""
    aleatoric = beta / (alpha - 1.0)
    epistemic = beta / (nu * (alpha - 1.0))
    return gamma, aleatoric, epistemic
