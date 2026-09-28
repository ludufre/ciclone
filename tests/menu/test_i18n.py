"""Idiomas: o browser sobe no idioma do config.yml, com o texto dos dicts lang_*.py e sem
glifo desconhecido na tela (um caractere fora do ACCENTS/HOMOGLYPHS vira lixo em silêncio)."""
import ciclone as c


def _check_language(t, idx):
    lang = c.LANGS[idx]
    m = t.menu(t.sd(config=f"---\nLanguage: {idx}\n"))
    assert m.u8("cur_lang") == idx
    want = c.encode_menu_text(c.tr("text_statusbar_keys", lang))
    bar = m.statusbar()
    assert bar.startswith(want), f"{lang}: barra {bar!r}, esperado {want!r}"
    assert c.UNKNOWN not in m.text(), f"{lang}: glifo desconhecido na tela\n{m.text()}"
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    fav = c.encode_menu_text(c.tr("text_filesel_context_add_to_favorites", lang))
    assert m.has(fav), f"{lang}: menu de contexto sem {fav!r}\n{m.text()}"
    assert c.UNKNOWN not in m.text(), f"{lang}: glifo desconhecido no menu de contexto\n{m.text()}"


# um teste por idioma (roda em paralelo e a falha diz qual)
for _i, _lang in enumerate(c.LANGS):
    def _mk(i):
        def test(t):
            _check_language(t, i)
        return test
    _fn = _mk(_i)
    _fn.__name__ = f"test_language_{_i}_{_lang}"
    _fn.__module__ = __name__
    globals()[_fn.__name__] = _fn
