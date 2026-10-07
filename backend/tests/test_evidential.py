import math

import torch

from foodtrace.model.nets import EvidentialNet, evidential_loss, nig_moments, nig_nll


def test_outputs_respect_parameter_constraints():
    net = EvidentialNet(n_seq=8, n_static=3)
    g, nu, a, b = net(torch.randn(16, 24, 8), torch.randn(16, 3))
    assert (nu > 0).all() and (a > 1).all() and (b > 0).all()


def test_moments_match_closed_form():
    g, nu, a, b = map(torch.tensor, (0.5, 2.0, 3.0, 4.0))
    _, alea, epi = nig_moments(g, nu, a, b)
    assert math.isclose(alea.item(), 4.0 / 2.0)
    assert math.isclose(epi.item(), 4.0 / (2.0 * 2.0))


def test_more_evidence_means_less_epistemic_uncertainty():
    b, a = torch.tensor(1.0), torch.tensor(3.0)
    _, _, low_nu = nig_moments(0, torch.tensor(1.0), a, b)
    _, _, high_nu = nig_moments(0, torch.tensor(10.0), a, b)
    assert high_nu < low_nu


def test_nll_is_lower_when_prediction_is_right():
    nu, a, b = torch.tensor(2.0), torch.tensor(3.0), torch.tensor(1.0)
    near = nig_nll(torch.tensor(0.0), torch.tensor(0.0), nu, a, b)
    far = nig_nll(torch.tensor(3.0), torch.tensor(0.0), nu, a, b)
    assert near < far


def test_a_few_steps_of_training_reduce_the_loss():
    torch.manual_seed(0)
    x, s = torch.randn(256, 24, 4), torch.randn(256, 2)
    y = x[:, -1, 0] * 0.8
    net = EvidentialNet(4, 2)
    opt = torch.optim.Adam(net.parameters(), lr=3e-3)
    first = evidential_loss(y, *net(x, s), 0.01).item()
    for _ in range(150):
        loss = evidential_loss(y, *net(x, s), 0.01)
        opt.zero_grad(); loss.backward(); opt.step()
    assert loss.item() < first
