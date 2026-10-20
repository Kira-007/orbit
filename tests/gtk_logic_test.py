"""Unit tests for the GTK build's non-UI modules."""
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
os.environ['XDG_STATE_HOME'] = tempfile.mkdtemp()

from orbit import settings  # noqa: E402
from orbit.desktop_ipc import desktop_url  # noqa: E402
from orbit.notifications import NotificationFeed, task_key  # noqa: E402
from orbit.sprite import DragDirection, pet_state  # noqa: E402
from orbit.store import Store, codex_event  # noqa: E402
from orbit.usage import normalize_agy, normalize_claude, normalize_codex  # noqa: E402

NOW = 1_800_000_000_000


class StoreTest(unittest.TestCase):
    def test_rejects_invalid_and_older_events(self):
        store = Store()
        self.assertFalse(store.update({'provider': 'nope', 'status': 'working', 'session': 'a', 'time': 1}))
        self.assertTrue(store.update({'provider': 'claude', 'status': 'working', 'session': 'a', 'time': 10, 'workspace': '/x/proj'}))
        self.assertFalse(store.update({'provider': 'claude', 'status': 'done', 'session': 'a', 'time': 5}))
        self.assertEqual(store.sessions['claude:a']['title'], 'proj')

    def test_snapshot_marks_stale_and_sorts(self):
        store = Store()
        store.update({'provider': 'claude', 'status': 'working', 'session': 'old', 'time': NOW - 1_000_000})
        store.update({'provider': 'claude', 'status': 'waiting', 'session': 'new', 'time': NOW})
        sessions = store.snapshot(NOW)['sessions']
        self.assertEqual([s['status'] for s in sessions], ['waiting', 'unknown'])

    def test_codex_event(self):
        meta = {'id': 's1', 'cwd': '/w', 'originator': 'codex_cli'}
        event = codex_event({'type': 'event_msg', 'timestamp': '2027-01-01T00:00:00Z', 'payload': {'type': 'user_message', 'message': ' fix  bug '}}, meta, 0)
        self.assertEqual((event['provider'], event['status'], event['title']), ('codex-cli', 'working', 'fix bug'))
        self.assertIn('taskStartedAt', event)
        self.assertIsNone(codex_event({'type': 'event_msg', 'payload': {'type': 'task_started'}}, {**meta, 'parent_thread_id': 'p'}, 0))
        self.assertIsNone(codex_event({'type': 'event_msg', 'payload': {'type': 'task_started'}}, {**meta, 'source': {'subagent': True}}, 0))


class NotificationTest(unittest.TestCase):
    def session(self, **extra):
        return {'provider': 'claude', 'session': 's', 'status': 'working', 'time': NOW, 'title': 'Task', **extra}

    def test_completed_tasks_expire(self):
        feed = NotificationFeed()
        self.assertEqual(len(feed.update([self.session(status='done')], 10, NOW)), 1)
        self.assertEqual(feed.update([self.session(status='done')], 10, NOW + 11 * 60000), [])

    def test_dismiss_until_new_run(self):
        feed = NotificationFeed()
        feed.dismiss(self.session(), NOW)
        self.assertEqual(feed.update([self.session()], 10, NOW), [])
        self.assertEqual(len(feed.update([self.session(time=NOW + 1000, title='Another')], 10, NOW + 1000)), 1)

    def test_codex_providers_share_key(self):
        self.assertEqual(task_key({'provider': 'codex-cli', 'session': 'x'}), task_key({'provider': 'codex-desktop', 'session': 'x'}))


class UsageTest(unittest.TestCase):
    def test_normalizers(self):
        self.assertEqual(normalize_codex({'primary': {'used_percent': 30, 'resets_at': 10}}, 1)['windows'][0]['remaining'], 70)
        self.assertEqual(normalize_agy({'time': 1, 'quota': {'q': {'remaining_fraction': .25}}})['windows'][0]['remaining'], 25)
        self.assertIsNone(normalize_agy({'time': 1, 'quota': {'q': {'remaining_fraction': 2}}}))
        claude = normalize_claude({'five_hour': {'utilization': 12.4, 'resets_at': '2027-01-01T00:00:00Z'}}, 1)
        self.assertEqual(claude['windows'][0], {'label': 'Session', 'remaining': 88, 'reset': 1798761600000})


class SettingsTest(unittest.TestCase):
    def test_normalize_clamps_and_defaults(self):
        value = settings.normalize({'petScale': 9, 'hoverDelay': 3, 'bodyColor': 'red', 'face': 'sleepy',
                                    'spritePets': [{'id': 'a', 'spriteSheets': {'idle': {'sheet': 'file:///x.png', 'frames': 999}}}]})
        self.assertEqual((value['petScale'], value['hoverDelay'], value['bodyColor'], value['face']), (2.4, 750, '#90bbb7', 'sleepy'))
        self.assertEqual(value['spritePets'][0]['spriteSheets']['idle']['frames'], 256)
        self.assertEqual(value['petMode'], 'sprite')

    def test_bundled_pets_use_file_urls(self):
        sheet = settings.bundled_pets()[0]['spriteSheets']['idle']['sheet']
        self.assertTrue(sheet.startswith('file:///'))
        self.assertTrue(pathlib.Path(settings.sheet_path(sheet)).exists())


class MotionTest(unittest.TestCase):
    def test_drag_direction_needs_a_confirmed_turn(self):
        direction = DragDirection(0, 1)
        self.assertEqual(direction.update(50, 0), 1)
        self.assertEqual(direction.update(40, .01), 1)
        self.assertEqual(direction.update(20, .2), -1)

    def test_pet_state(self):
        self.assertEqual(pet_state([{'status': 'done', 'time': NOW}, {'status': 'working', 'time': 0}], NOW), 'working')
        self.assertEqual(pet_state([{'status': 'error', 'time': NOW - 60000}], NOW), 'idle')

    def test_desktop_url(self):
        self.assertEqual(desktop_url('0' * 8 + '-0000-0000-0000-' + '0' * 12), 'codex://threads/00000000-0000-0000-0000-000000000000')
        with self.assertRaises(ValueError):
            desktop_url('../x')


if __name__ == '__main__':
    unittest.main()
