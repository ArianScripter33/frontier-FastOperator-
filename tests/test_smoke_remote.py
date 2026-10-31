"""No network, models, or desktop access: exercise the remote verification gate."""
import pytest
import smoke_remote as smoke


@pytest.mark.parametrize('state,expected', [
    ({'estado': 'terminada', 'resumen': 'respuesta: 45\nConté todas las páginas.'}, True),
    ({'estado': 'terminada', 'resumen': 'respuesta: 145'}, False),
    ({'estado': 'fallida', 'resumen': 'respuesta: 45'}, False),
    ({'estado': 'terminada', 'resumen': 'Conté 45.'}, False),
    ({'estado': 'terminada', 'resumen': 'respuesta: 45\nrespuesta: 46'}, False),
])
def test_answer_gate(state, expected):
    assert smoke.correct_answer(state, "45") is expected


def test_missing_url_has_usage_not_index_error():
    with pytest.raises(SystemExit) as exc:
        smoke.main([])
    assert exc.value.code == 2


@pytest.mark.parametrize('accept,estado,answer,exit_code', [
    (0.37, 'terminada', '45', 0),
    (2.1, 'terminada', '45', 1),
    (0.37, 'fallida', '45', 1),
    (0.37, 'terminada', '145', 1),
])
def test_full_gate_without_network(monkeypatch, accept, estado, answer, exit_code):
    for name in ('FRONTIER_TEAM_TOKEN', 'FRONTIER_DESKTOP_URL', 'FRONTIER_DESKTOP_PASSWORD'):
        monkeypatch.setenv(name, 'https://example.invalid' if name.endswith('URL') else 'fixture')
    now = [0.0]
    monkeypatch.setattr(smoke.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(smoke.time, 'sleep', lambda value: now.__setitem__(0, now[0] + value))
    posts = []

    def fake_call(base, path, token=None, body=None):
        if path == '/health':
            return 200, {'ok': True}
        if path == '/tasks':
            posts.append(body)
            now[0] += accept
            return 200, {'task_id': 'fixture-task'}
        return 200, {'estado': estado, 'resumen': 'respuesta: ' + answer}

    monkeypatch.setattr(smoke, 'call', fake_call)
    assert smoke.main(['https://example.invalid']) == exit_code
    assert len(posts) == 1
