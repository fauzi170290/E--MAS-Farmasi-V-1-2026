from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as Obj
import json
import pytest

from emss.alerts.notification import notification_decision, CLEAR_MESSAGE
from emss.alerts.audio import AudioPreferences, CATEGORIES, resolve_audio_path, validate_audio_file
from emss.services.monitor_lock import MonitorProcessLock


def clear_result():
    return Obj(risk_status='SAFE', completeness_status='COMPLETE', ingredient_count=2,
        interaction_count=0, not_assessed_count=0, unmapped_drug_count=0, pair_count=1,
        assessed_no_interaction_count=1)


def test_clear_requires_explicit_complete_assessment_and_validation():
    result = clear_result()
    pair = Obj(classification='ASSESSED_NO_INTERACTION', severity_code='NONE')
    decision, category = notification_decision(result, [pair], [], validated=True)
    assert category == 'screening-clear' and decision.message == CLEAR_MESSAGE
    for validated, issues, pairs in [(False, [], [pair]), (True, [Obj()], [pair]), (True, [], [])]:
        assert notification_decision(result, pairs, issues, validated=validated)[1] != 'screening-clear'
    result.completeness_status = 'NOT_ASSESSED'
    assert notification_decision(result, [pair], [], validated=True)[1] == ''


def test_critical_safety_warning_is_not_a_contraindication_sound():
    result = clear_result()
    result.risk_status = 'CRITICAL'
    decision, category = notification_decision(result, [], [Obj()], validated=True)
    assert decision.notify and category == ''
    assert notification_decision(result, [Obj(classification='PAIR_NOT_ASSESSED', severity_code='CONTRAINDICATED')], [], validated=True)[1] == ''


def test_validated_high_alert_medication_has_its_own_audio_without_popup():
    result = clear_result()
    issue = Obj(issue_type='HIGH_ALERT')
    decision, category = notification_decision(
        result, [], [issue], validated=True, validated_high_only=True
    )
    assert category == 'high-alert'
    assert decision.level == 'AUDIO' and decision.notify and not decision.persistent


def test_validated_significant_and_duplicate_each_have_review_popup():
    result = clear_result()
    result.risk_status = 'REVIEW'
    pair = Obj(classification='INTERACTION_FOUND', severity_code='SIGNIFICANT')
    decision, category = notification_decision(
        result, [pair], [], validated=True, validated_high_only=True
    )
    assert category == 'significant-review' and decision.notify and decision.persistent
    duplicate = Obj(issue_type='DUPLICATE_THERAPY')
    decision, category = notification_decision(
        result, [], [duplicate], validated=True, validated_high_only=True
    )
    assert category == 'duplicate' and decision.notify and 'apakah obat tersebut masih digunakan' in decision.message.lower()


@pytest.mark.parametrize('severity, category', [
    ('CONTRAINDICATED', 'contraindicated'), ('SERIOUS', 'major'),
])
def test_duplicate_is_secondary_to_validated_high_risk_interaction(severity, category):
    result = clear_result()
    result.risk_status = 'CRITICAL' if severity == 'CONTRAINDICATED' else 'HIGH_RISK'
    pair = Obj(classification='INTERACTION_FOUND', severity_code=severity)
    duplicate = Obj(issue_type='DUPLICATE_THERAPY', message='Kandungan obat sama dalam resep')

    decision, actual = notification_decision(
        result, [pair], [duplicate], validated=True, validated_high_only=True
    )

    assert actual == category
    assert decision.title in {'KONTRAINDIKASI', 'MAYOR'}
    assert 'Temuan tambahan: potensi duplikasi obat.' in decision.message


def test_audio_preferences_roundtrip_and_corrupt_config(tmp_path):
    path = tmp_path / 'audio.json'
    prefs = AudioPreferences()
    prefs.volume = 32
    prefs.save(path)
    assert AudioPreferences.load(path).volume == 32
    for raw in ['{', '{}', '{"volume": 200, "paths": {}}', '{"volume":0,"paths":null}']:
        path.write_text(raw)
        assert AudioPreferences.load(path).volume == 75
    prefs.volume = 0
    with pytest.raises(ValueError): prefs.save(path)
    prefs.volume = -1
    with pytest.raises(ValueError): prefs.save(path)


def test_original_bundled_audio_is_complete_and_valid():
    preferences = AudioPreferences()
    assert set(preferences.paths) == set(CATEGORIES)
    for category in CATEGORIES:
        assert validate_audio_file(preferences.paths[category]).name == f'{category}.wav'


def test_old_three_sound_preferences_gain_bundled_high_alert_on_upgrade(tmp_path):
    path = tmp_path / 'audio.json'
    old = {key: f'C:/audio/{key}.wav' for key in CATEGORIES if key != 'high-alert'}
    path.write_text(json.dumps({'volume': 44, 'paths': old}), encoding='utf-8')
    loaded = AudioPreferences.load(path)
    assert loaded.volume == 44
    assert loaded.paths['major'] == 'C:/audio/major.wav'
    assert Path(loaded.paths['high-alert']).name == 'high-alert.wav'


@pytest.mark.parametrize('name', ['screening-clear.wav', 'major.wav', 'contraindicated.wav'])
def test_user_wavs_valid_without_conversion(name):
    source = Path(__file__).resolve().parents[2] / 'docs' / 'audio-intake' / name
    assert validate_audio_file(str(source)) == source


def test_audio_missing_corrupt_remote_and_unsupported(tmp_path):
    broken = tmp_path / 'broken.wav'
    broken.write_bytes(b'broken')
    unsupported = tmp_path / 'sound.txt'
    unsupported.write_text('text')
    for path in ['', 'relative.wav', r'\\host\sound.wav', str(tmp_path / 'missing.wav'), str(broken), str(unsupported)]:
        with pytest.raises(ValueError): validate_audio_file(path)
    mp3 = tmp_path / 'sample.mp3'
    mp3.write_bytes(b'ID3')
    assert validate_audio_file(str(mp3)) == mp3  # Decoder checks MP3 content; visual fallback is tested separately.


def test_missing_custom_audio_resolves_to_bundled_category(tmp_path):
    fallback, used_fallback = resolve_audio_path(
        'screening-clear', str(tmp_path / 'Downloads' / 'gone.wav')
    )
    assert used_fallback
    assert fallback is not None
    assert fallback.name == 'screening-clear.wav'
    assert validate_audio_file(fallback) == fallback


def test_valid_custom_audio_is_not_replaced(tmp_path):
    source = Path(__file__).resolve().parents[2] / 'docs' / 'audio-intake' / 'screening-clear.wav'
    resolved, used_fallback = resolve_audio_path('screening-clear', str(source))
    assert resolved == source
    assert not used_fallback


def test_monitor_os_lock_prevents_second_worker_and_releases(tmp_path):
    first, second = MonitorProcessLock(tmp_path / 'monitor.lock'), MonitorProcessLock(tmp_path / 'monitor.lock')
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.release()
    assert second.acquire()
    second.release()


def test_credential_diagnostics_never_return_or_replace_secrets(monkeypatch):
    import os
    from emss.integrations.khanza import credentials
    monkeypatch.setattr(credentials, 'machine_credential', lambda: None)
    monkeypatch.delenv('EMSS_KHANZA_PASSWORD', raising=False)
    assert 'belum tersedia' in credentials.credential_diagnostic()
    monkeypatch.setenv('EMSS_KHANZA_PASSWORD', 'synthetic-process-secret')
    assert credentials.connection_password() == 'synthetic-process-secret'
    monkeypatch.setattr(credentials, 'machine_credential', lambda: 'synthetic-machine-secret')
    assert 'berbeda' in credentials.credential_diagnostic()
    assert credentials.connection_password() == 'synthetic-machine-secret'
    assert os.environ['EMSS_KHANZA_PASSWORD'] == 'synthetic-process-secret'
    monkeypatch.setattr(credentials, 'machine_credential', lambda: 'synthetic-process-secret')
    assert 'nilai tidak ditampilkan' in credentials.credential_diagnostic()


def test_audio_rejects_truncated_pcm_and_overlong_duration(tmp_path):
    import wave
    short = tmp_path / 'truncated.wav'
    with wave.open(str(short), 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(100)
        writer.writeframes(b'\0' * 200)
    short.write_bytes(short.read_bytes()[:-10])
    with pytest.raises(ValueError, match='terpotong'): validate_audio_file(str(short))
    long = tmp_path / 'long.wav'
    with wave.open(str(long), 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(100)
        writer.writeframes(b'\0' * 6200)
    with pytest.raises(ValueError, match='30 detik'): validate_audio_file(str(long))


@pytest.mark.ui
def test_audio_player_visual_fallback_device_mute_and_corrupt(qtbot, monkeypatch, tmp_path):
    from emss.ui.tray.audio import AlertAudioPlayer, QMediaDevices
    player = AlertAudioPlayer()
    errors = []
    player.failed.connect(errors.append)
    wav = Path(__file__).resolve().parents[2] / 'docs/audio-intake/major.wav'
    monkeypatch.setattr(QMediaDevices, 'audioOutputs', lambda: [])
    assert not player.play(str(wav), 50)
    assert 'Perangkat' in errors[-1]
    monkeypatch.setattr(QMediaDevices, 'audioOutputs', lambda: [object()])
    assert not player.play(str(wav), 0)
    assert 'mute' in errors[-1]
    broken = tmp_path / 'bad.wav'
    broken.write_bytes(b'corrupt')
    assert not player.play(str(broken), 50)
    assert 'rusak' in errors[-1]
