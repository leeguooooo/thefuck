def test_readme(source_root):
    with source_root.joinpath('README.md').open() as f:
        readme = f.read()

        assert '# fuck' in readme
        assert 'uv tool install fuck-cli' in readme
        assert 'fuck setup' in readme
        assert 'Disclaimer:' in readme
        assert '免责声明' in readme
        assert '免責事項' in readme
