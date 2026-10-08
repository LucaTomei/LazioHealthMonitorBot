"""
Test d'integrazione del bot: gli handler reali girano su un'Application PTB vera,
con un finto server Telegram (nessuna rete) e un database SQLite temporaneo.
Le API della Regione Lazio sono sostituite da funzioni finte.

Esecuzione:  python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

TMP = tempfile.mkdtemp(prefix="laziobot-test-")
os.environ.update({
    "TELEGRAM_BOT_TOKEN": "123456:TEST",
    "DB_FILE": os.path.join(TMP, "data", "test.db"),
    "LOG_FOLDER": os.path.join(TMP, "logs"),
    "PDF_FOLDER": os.path.join(TMP, "pdf"),
    "REPORTS_FOLDER": os.path.join(TMP, "reports"),
    "DEBUG_FOLDER": os.path.join(TMP, "debug"),
    "INPUT_FILE": os.path.join(TMP, "none.json"),
    "PREVIOUS_DATA_FILE": os.path.join(TMP, "none.json"),
    "USERS_FILE": os.path.join(TMP, "none.json"),
    "REPORTS_MONITORING_FILE": os.path.join(TMP, "none.json"),
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

from telegram.request import BaseRequest  # noqa: E402
from telegram.ext import Application  # noqa: E402

import config  # noqa: E402
from modules import database, data_utils, bot_handlers, reports_monitor, prescription_processor  # noqa: E402

ADMIN = 1001
USER = 2002
OTHER = 3003
CF = "RSSMRA80A01H501U"
NRE = "1200A1234567890"


class FakeTelegram(BaseRequest):
    """Finto server Bot API: registra ogni chiamata e risponde con oggetti validi."""

    def __init__(self):
        self.calls = []
        self._message_id = 100

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    @property
    def read_timeout(self):
        return 5

    def _message(self, params):
        self._message_id += 1
        return {
            "message_id": params.get("message_id", self._message_id),
            "date": 0,
            "chat": {"id": int(params.get("chat_id", 1)), "type": "private"},
            "text": params.get("text", ""),
        }

    async def do_request(self, url, method, request_data=None, **kwargs):
        api_method = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        self.calls.append((api_method, params))
        if api_method == "getMe":
            result = {"id": 999, "is_bot": True, "first_name": "Bot", "username": "test_bot",
                      "can_join_groups": True, "can_read_all_group_messages": False,
                      "supports_inline_queries": False}
        elif api_method in ("sendMessage", "editMessageText", "sendDocument", "editMessageReplyMarkup"):
            result = self._message(params)
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()

    # Helper per le asserzioni
    def texts(self):
        return [p.get("text", "") for m, p in self.calls if m in ("sendMessage", "editMessageText")]

    def last_text(self):
        texts = self.texts()
        return texts[-1] if texts else ""

    def methods(self):
        return [m for m, _ in self.calls]

    def buttons(self):
        """callback_data dell'ultima tastiera inline inviata."""
        for method, params in reversed(self.calls):
            markup = params.get("reply_markup")
            if markup:
                markup = json.loads(markup) if isinstance(markup, str) else markup
                if "inline_keyboard" in markup:
                    return [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        return []


class BotTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Database pulito per ogni test
        if os.path.exists(os.environ["DB_FILE"]):
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(os.environ["DB_FILE"] + suffix)
                except FileNotFoundError:
                    pass
        database.init_db()
        config.authorized_users.clear()
        config.authorized_users.extend([str(ADMIN), str(USER)])
        data_utils.save_authorized_users()
        config.user_data.clear()
        bot_handlers.quickbook_sessions.clear()
        bot_handlers.report_sessions.clear()

        self.tg = FakeTelegram()
        self.app = Application.builder().token("123456:TEST").request(self.tg).get_updates_request(FakeTelegram()).build()
        bot_handlers.setup_handlers(self.app)
        await self.app.initialize()
        self._update_id = 0
        self._msg_id = 1

    async def asyncTearDown(self):
        await self.app.shutdown()

    def _user(self, user_id):
        return {"id": user_id, "is_bot": False, "first_name": f"U{user_id}"}

    async def send(self, user_id, text):
        self._update_id += 1
        self._msg_id += 1
        message = {"message_id": self._msg_id, "date": 0, "chat": {"id": user_id, "type": "private"},
                   "from": self._user(user_id), "text": text}
        if text.startswith("/"):
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        update = {"update_id": self._update_id, "message": message}
        self.tg.calls.clear()
        await self.app.process_update(self._de_json(update))

    async def click(self, user_id, data):
        self._update_id += 1
        update = {
            "update_id": self._update_id,
            "callback_query": {
                "id": str(self._update_id), "from": self._user(user_id), "chat_instance": "x", "data": data,
                "message": {"message_id": 50, "date": 0, "chat": {"id": user_id, "type": "private"}, "text": "menu"},
            },
        }
        self.tg.calls.clear()
        await self.app.process_update(self._de_json(update))

    def _de_json(self, data):
        from telegram import Update
        return Update.de_json(data, self.app.bot)

    def answers(self):
        return [p for m, p in self.tg.calls if m == "answerCallbackQuery"]

    def add_prescription_row(self, owner=USER, **extra):
        p = {"fiscal_code": CF, "nre": NRE, "telegram_chat_id": owner, "notifications_enabled": True,
             "auto_book_enabled": False, "phone": "3331234567", "email": "a@b.it",
             "description": "VISITA CARDIOLOGICA", "config": {"months_limit": None}}
        p.update(extra)
        data_utils.add_prescription(p)
        return p


# =============================================================================
# DATI
# =============================================================================

class DataLayerTests(BotTestCase):
    async def test_stale_snapshot_cannot_delete_or_revert(self):
        self.add_prescription_row()
        stale = data_utils.load_input_data()  # copia letta da un processo
        other = dict(stale[0], nre="1200A0000000001", description="ALTRA")
        data_utils.add_prescription(other)  # l'altro processo aggiunge una prescrizione
        data_utils.update_prescription(CF, NRE, lambda p: p.__setitem__("bookings", [{"booking_id": "B1"}]))
        # Il primo processo salva la sua copia vecchia: non deve perdere nulla
        data_utils.save_input_data(stale)
        nres = {p["nre"] for p in data_utils.load_input_data()}
        self.assertEqual(nres, {NRE, "1200A0000000001"})

    async def test_update_prescription_is_atomic_and_keeps_fields(self):
        self.add_prescription_row()
        data_utils.update_prescription(CF, NRE, lambda p: p.__setitem__("auto_book_enabled", True))
        data_utils.update_prescription(CF, NRE, lambda p: p.__setitem__("notifications_enabled", False))
        p = data_utils.get_prescription(CF, NRE)
        self.assertTrue(p["auto_book_enabled"])
        self.assertFalse(p["notifications_enabled"])
        self.assertEqual(p["description"], "VISITA CARDIOLOGICA")
        self.assertIsNone(data_utils.update_prescription(CF, "NOPE", lambda p: None))

    async def test_delete_removes_previous_availabilities(self):
        self.add_prescription_row()
        data_utils.save_previous_data({f"{CF}_{NRE}": [{"date": "x"}], "orphan_key": []})
        data_utils.prune_previous_data()
        self.assertEqual(set(data_utils.load_previous_data()), {f"{CF}_{NRE}"})
        data_utils.delete_prescription(CF, NRE)
        self.assertEqual(data_utils.load_previous_data(), {})

    async def test_load_raises_instead_of_returning_empty(self):
        with mock.patch.object(data_utils, "get_connection", side_effect=RuntimeError("db locked")):
            with self.assertRaises(RuntimeError):
                data_utils.load_input_data()

    async def test_dates_use_rome_day_and_utc_now(self):
        # 21:50Z e 22:10Z sono lo stesso giorno UTC ma giorni diversi a Roma (estate, UTC+2)
        self.assertFalse(data_utils.is_similar_datetime("2030-07-01T21:50:00Z", "2030-07-01T22:10:00Z", 60))
        self.assertTrue(data_utils.is_similar_datetime("2030-07-01T08:00:00Z", "2030-07-01T08:30:00Z", 60))
        self.assertEqual(data_utils.fmt_datetime("2030-07-01T08:00:00Z"), "01/07/2030 10:00")
        self.assertTrue(data_utils.is_date_within_range("2099-01-01T00:00:00Z", None))
        self.assertFalse(data_utils.is_date_within_range("2000-01-01T00:00:00Z", 2))

    async def test_json_migration_runs_once(self):
        path = os.path.join(TMP, "input_once.json")
        with open(path, "w") as f:
            json.dump([{"fiscal_code": CF, "nre": NRE}], f)
        with mock.patch.object(config, "INPUT_FILE", path):
            # Il DB di test è già marcato come migrato: il file non deve essere reimportato
            database.migrate_from_json()
        self.assertEqual(data_utils.load_input_data(), [])


# =============================================================================
# ACCESSO E NAVIGAZIONE
# =============================================================================

class NavigationTests(BotTestCase):
    async def test_unauthorized_user_rejected(self):
        await self.send(OTHER, "📋 Lista Prescrizioni")
        self.assertIn("Non sei autorizzato", self.tg.last_text())

    async def test_first_user_becomes_admin_only_if_db_empty(self):
        config.authorized_users.clear()
        await self.send(OTHER, "ciao")  # nel DB ci sono ancora utenti
        self.assertIn("Non sei autorizzato", self.tg.last_text())
        with database.get_connection() as conn:
            conn.execute("DELETE FROM users")
        await self.send(OTHER, "ciao")
        self.assertIn("amministratore", self.tg.last_text())
        self.assertEqual(config.authorized_users, [str(OTHER)])

    async def test_menu_button_during_text_input_switches_operation(self):
        await self.send(USER, "➕ Aggiungi Prescrizione")
        await self.send(USER, "📋 Lista Prescrizioni")
        self.assertIn("Non hai prescrizioni", self.tg.last_text())
        await self.send(USER, "testo qualsiasi")  # non deve essere letto come codice fiscale
        self.assertIn("Usa i pulsanti", self.tg.last_text())

    async def test_cancel_command_closes_conversation(self):
        await self.send(USER, "➕ Aggiungi Prescrizione")
        await self.send(USER, "/cancel")
        self.assertIn("Operazione annullata", self.tg.last_text())
        await self.send(USER, CF)
        self.assertIn("Usa i pulsanti", self.tg.last_text())

    async def test_stale_button_is_answered(self):
        await self.click(USER, "slot_3")
        self.assertEqual(len(self.answers()), 1)
        self.assertIn("non è più valido", self.answers()[0].get("text", ""))

    async def test_foreign_button_does_not_confirm_add(self):
        await self.send(USER, "➕ Aggiungi Prescrizione")
        await self.send(USER, CF)
        await self.send(USER, NRE)
        await self.send(USER, "3331234567")
        await self.send(USER, "a@b.it")
        await self.click(USER, f"quickbook_{CF}_{NRE}")
        self.assertEqual(data_utils.load_input_data(), [])


# =============================================================================
# PRESCRIZIONI
# =============================================================================

class PrescriptionTests(BotTestCase):
    async def _add_flow(self, verify_result):
        with mock.patch.object(bot_handlers, "process_prescription", return_value=verify_result) as proc:
            await self.send(USER, "➕ Aggiungi Prescrizione")
            await self.send(USER, "rssmra80a01h501u")
            await self.send(USER, NRE)
            await self.send(USER, "333 123 4567")
            await self.send(USER, "non-una-email")
            self.assertIn("non sembra valida", self.tg.last_text())
            await self.send(USER, "mario@example.com")
            await self.click(USER, "confirm_add")
            return proc

    async def test_add_saved_even_without_availability(self):
        await self._add_flow((False, "Prescrizione non disponibile al momento"))
        p = data_utils.get_prescription(CF, NRE)
        self.assertIsNotNone(p)
        self.assertEqual(p["phone"], "3331234567")
        self.assertTrue(any("continuerà comunque a controllarla" in t for t in self.tg.texts()))

    async def test_add_success_and_duplicate_rejected(self):
        await self._add_flow((True, "VISITA"))
        self.assertIsNotNone(data_utils.get_prescription(CF, NRE))
        await self.send(USER, "➕ Aggiungi Prescrizione")
        await self.send(USER, CF)
        await self.send(USER, NRE)
        self.assertIn("già presente", self.tg.last_text())

    async def test_add_survives_verification_crash(self):
        with mock.patch.object(bot_handlers, "process_prescription", side_effect=RuntimeError("boom")):
            await self.send(USER, "➕ Aggiungi Prescrizione")
            await self.send(USER, CF)
            await self.send(USER, NRE)
            await self.send(USER, "3331234567")
            await self.send(USER, "a@b.it")
            await self.click(USER, "confirm_add")
        self.assertIsNotNone(data_utils.get_prescription(CF, NRE))

    async def test_remove(self):
        self.add_prescription_row()
        await self.send(USER, "➖ Rimuovi Prescrizione")
        await self.click(USER, "remove_0")
        self.assertIn("rimossa con successo", self.tg.last_text())
        self.assertIsNone(data_utils.get_prescription(CF, NRE))

    async def test_user_sees_only_own_prescriptions_admin_sees_all(self):
        self.add_prescription_row(owner=USER)
        data_utils.add_prescription({"fiscal_code": "BNCLRA85M41H501X", "nre": "1200A9999999999", "telegram_chat_id": ADMIN})
        await self.send(USER, "📋 Lista Prescrizioni")
        self.assertNotIn("BNCLRA85M41H501X", self.tg.last_text())
        await self.send(ADMIN, "📋 Lista Prescrizioni")
        self.assertIn("BNCLRA85M41H501X", self.tg.last_text())
        self.assertIn(CF, self.tg.last_text())

    async def test_list_escapes_html_and_splits_long_messages(self):
        for i in range(60):
            data_utils.add_prescription({
                "fiscal_code": CF, "nre": f"1200A{i:010d}", "telegram_chat_id": USER,
                "description": "ESAME <SPECIALE> & CONTROLLO " + "X" * 40,
                "phone": "3331234567", "email": "a@b.it",
            })
        await self.send(USER, "📋 Lista Prescrizioni")
        texts = self.tg.texts()
        self.assertGreater(len(texts), 1)
        self.assertTrue(all(len(t) <= 4096 for t in texts))
        self.assertIn("&lt;SPECIALE&gt; &amp; CONTROLLO", texts[0])

    async def test_toggle_notifications(self):
        self.add_prescription_row()
        await self.send(USER, "🔔 Gestisci Notifiche")
        await self.click(USER, "toggle_0")
        self.assertFalse(data_utils.get_prescription(CF, NRE)["notifications_enabled"])
        self.assertEqual(len(self.answers()), 1)

    async def test_auto_booking_toggle(self):
        self.add_prescription_row()
        await self.send(USER, "🤖 Prenota Automaticamente")
        await self.click(USER, "auto_book_0")
        self.assertTrue(data_utils.get_prescription(CF, NRE)["auto_book_enabled"])

    async def test_date_filter_custom(self):
        self.add_prescription_row()
        await self.send(USER, "⏱ Imposta Filtro Date")
        await self.click(USER, "date_filter_0")
        await self.click(USER, "months_custom")
        await self.send(USER, "30")
        self.assertIn("compreso tra 1 e 24", self.tg.last_text())
        await self.send(USER, "4")
        await self.click(USER, "confirm_date_filter")
        self.assertEqual(data_utils.get_prescription(CF, NRE)["config"]["months_limit"], 4)

    async def test_date_filter_quick_choice_none(self):
        self.add_prescription_row(config={"months_limit": 3})
        await self.send(USER, "⏱ Imposta Filtro Date")
        await self.click(USER, "date_filter_0")
        await self.click(USER, "months_0")
        await self.click(USER, "confirm_date_filter")
        self.assertIsNone(data_utils.get_prescription(CF, NRE)["config"]["months_limit"])

    async def test_blacklist_flow_single_answer_per_click(self):
        self.add_prescription_row()
        data_utils.add_prescription({"fiscal_code": CF, "nre": "1200A0000000002", "telegram_chat_id": USER,
                                     "config": {"hospitals_blacklist": ["OSP B"]}})
        with database.get_connection() as conn:
            for name in ("OSP A", "OSP B", "OSP & C"):
                conn.execute("INSERT INTO locations (key, hospital, address) VALUES (?, ?, ?)", (name, name, "via"))
        await self.send(USER, "🚫 Blacklist Ospedali")
        nre_index = [p["nre"] for p in data_utils.load_input_data()].index(NRE)
        await self.click(USER, f"blacklist_{nre_index}")
        self.assertIn("OSP &amp; C", self.tg.last_text())
        await self.click(USER, "toggle_hospital_0")
        await self.click(USER, "blacklist_all")
        self.assertEqual(len(self.answers()), 1)
        await self.click(USER, "whitelist_all")
        await self.click(USER, "import_blacklist")
        await self.click(USER, "import_from_0")
        self.assertEqual(len(self.answers()), 1)
        await self.click(USER, "page_noop")
        await self.click(USER, "confirm_blacklist")
        self.assertEqual(data_utils.get_prescription(CF, NRE)["config"]["hospitals_blacklist"], ["OSP B"])

    async def test_check_availability_continues_after_error(self):
        self.add_prescription_row()
        data_utils.add_prescription({"fiscal_code": CF, "nre": "1200A0000000002", "telegram_chat_id": USER})
        calls = []

        def fake_process(prescription, previous, chat_id=None):
            calls.append(prescription["nre"])
            if len(calls) == 1:
                raise RuntimeError("API giù")
            previous[f"{prescription['fiscal_code']}_{prescription['nre']}"] = [{"date": "2030-01-01T08:00:00Z"}]
            return True, "ok"

        with mock.patch.object(bot_handlers, "process_prescription", side_effect=fake_process), \
                mock.patch.object(bot_handlers.asyncio, "sleep", new=mock.AsyncMock()):
            await self.send(USER, "🔄 Verifica Disponibilità")
        self.assertEqual(len(calls), 2)
        self.assertIn("1/2", self.tg.last_text())
        self.assertEqual(len(data_utils.load_previous_data()), 1)


# =============================================================================
# PRENOTAZIONI
# =============================================================================

SLOTS = {
    "success": True, "action": "list_slots", "service": "VISITA & CONTROLLO", "patient_id": "P1", "process_id": "PR1",
    "slots": [
        {"index": 0, "date": "2030-03-01T08:00:00Z", "diary_id": "D0", "hospital": "OSP <A>", "address": "Via 1", "price": 20},
        {"index": 1, "date": "2030-03-02T08:00:00Z", "diary_id": "D1", "hospital": "OSP B", "address": "Via 2", "price": 25},
    ],
}


def booked(pdf=b"%PDF-1.4"):
    return {"success": True, "action": "booked", "booking_id": "BK1", "pdf_path": None, "pdf_content": pdf,
            "appointment_date": "2030-03-02T08:00:00Z", "hospital": "OSP B", "address": "Via 2",
            "service": "VISITA & CONTROLLO"}


class BookingTests(BotTestCase):
    async def test_booking_books_exact_slot_and_saves_first(self):
        self.add_prescription_row()
        calls = []

        def workflow(**kwargs):
            calls.append(kwargs)
            return SLOTS if kwargs.get("slot_choice") == -1 else booked()

        with mock.patch.object(bot_handlers, "booking_workflow", side_effect=workflow):
            await self.send(USER, "🏥 Prenota")
            await self.click(USER, "book_0")
            self.assertIn("OSP &lt;A&gt;", self.tg.last_text())
            await self.click(USER, "slot_1")
            await self.click(USER, "confirm_slot_1")
            # Doppio click sulla conferma: nessuna seconda prenotazione
            await self.click(USER, "confirm_slot_1")

        booking_calls = [c for c in calls if c.get("slot_choice") != -1]
        self.assertEqual(len(booking_calls), 1)
        self.assertEqual(booking_calls[0]["slot_date"], "2030-03-02T08:00:00Z")
        self.assertEqual(booking_calls[0]["diary_id"], "D1")
        p = data_utils.get_prescription(CF, NRE)
        self.assertEqual(p["bookings"][0]["booking_id"], "BK1")
        self.assertFalse(p["auto_book_enabled"])

    async def test_booking_saved_even_if_telegram_fails_and_without_pdf(self):
        self.add_prescription_row()

        def workflow(**kwargs):
            return SLOTS if kwargs.get("slot_choice") == -1 else booked(pdf=None)

        with mock.patch.object(bot_handlers, "booking_workflow", side_effect=workflow):
            await self.send(USER, "🏥 Prenota")
            await self.click(USER, "book_0")
            await self.click(USER, "slot_0")
            await self.click(USER, "confirm_slot_0")
        self.assertEqual(len(data_utils.get_prescription(CF, NRE)["bookings"]), 1)
        self.assertIn("non è al momento scaricabile", self.tg.last_text())
        self.assertNotIn("sendDocument", self.tg.methods())

    async def test_booking_asks_contacts_when_missing_and_saves_them(self):
        self.add_prescription_row(phone=None, email=None)
        with mock.patch.object(bot_handlers, "booking_workflow", return_value=SLOTS):
            await self.send(USER, "🏥 Prenota")
            await self.click(USER, "book_0")
            await self.send(USER, "3339876543")
            await self.send(USER, "nuova@mail.it")
        p = data_utils.get_prescription(CF, NRE)
        self.assertEqual((p["phone"], p["email"]), ("3339876543", "nuova@mail.it"))
        self.assertIn("slot_0", self.tg.buttons())

    async def test_slot_list_is_capped(self):
        self.add_prescription_row()
        many = dict(SLOTS, slots=[dict(SLOTS["slots"][0], index=i, date=f"2030-04-{i % 28 + 1:02d}T08:00:00Z")
                                  for i in range(60)])
        with mock.patch.object(bot_handlers, "booking_workflow", return_value=many):
            await self.send(USER, "🏥 Prenota")
            await self.click(USER, "book_0")
        self.assertLessEqual(len(self.tg.last_text()), 4096)
        self.assertIn("…e altre 40", self.tg.last_text())

    async def test_quickbook_requires_ownership(self):
        self.add_prescription_row(owner=ADMIN)
        with mock.patch.object(bot_handlers, "booking_workflow", return_value=SLOTS) as wf:
            await self.click(USER, f"quickbook_{CF}_{NRE}")
            self.assertIn("non trovata", self.tg.last_text())
            await self.click(OTHER, f"quickbook_{CF}_{NRE}")
            self.assertIn("Non sei autorizzato", self.answers()[0].get("text", ""))
            wf.assert_not_called()

    async def test_quickbook_flow(self):
        self.add_prescription_row()

        def workflow(**kwargs):
            return SLOTS if kwargs.get("slot_choice") == -1 else booked()

        with mock.patch.object(bot_handlers, "booking_workflow", side_effect=workflow):
            await self.click(USER, f"quickbook_{CF}_{NRE}")
            await self.click(USER, "qslot_0")
            await self.click(USER, "confirm_qslot_0")
        self.assertIn("sendDocument", self.tg.methods())
        self.assertEqual(data_utils.get_prescription(CF, NRE)["bookings"][0]["booking_id"], "BK1")

    async def test_list_and_cancel_booking(self):
        self.add_prescription_row(bookings=[{"booking_id": "LOCAL1", "date": "2030-05-01T08:00:00Z",
                                             "hospital": "OSP A", "address": "Via", "service": "VISITA"}])
        api = {"success": True, "bookings": [
            {"id": "API1", "startTime": None, "hospital": None, "site": None, "services": []},
            {"id": "LOCAL1", "startTime": "2030-05-01T08:00:00Z"},
        ]}
        with mock.patch.object(bot_handlers, "get_user_bookings", return_value=api), \
                mock.patch.object(bot_handlers, "cancel_booking", return_value={}) as cancel:
            await self.send(USER, "📝 Le mie Prenotazioni")
            listing = self.tg.last_text()
            self.assertIn("LOCAL1", listing)
            self.assertIn("API1", listing)
            self.assertEqual(listing.count("LOCAL1"), 1)
            await self.click(USER, "cancel_appointment")
            ids = [b["booking_id"] for b in config.user_data[USER]["bookings"]]
            self.assertEqual(sorted(ids), ["API1", "LOCAL1"])
            idx = ids.index("LOCAL1")
            await self.click(USER, f"cancel_book_{idx}")
            await self.click(USER, f"confirm_cancel_{idx}")
            cancel.assert_called_once_with("LOCAL1")
        self.assertIn("disdetta con successo", self.tg.last_text())

    async def test_cancel_booking_removes_local_record(self):
        self.add_prescription_row(bookings=[{"booking_id": "LOCAL1", "date": "2030-05-01T08:00:00Z",
                                             "hospital": "OSP A", "address": "Via", "service": "VISITA"}])
        with mock.patch.object(bot_handlers, "get_user_bookings", return_value={"success": False}), \
                mock.patch.object(bot_handlers, "cancel_booking", return_value={}):
            await self.click(USER, "cancel_appointment")
            await self.click(USER, "cancel_book_0")
            await self.click(USER, "confirm_cancel_0")
        self.assertEqual(data_utils.get_prescription(CF, NRE)["bookings"], [])


# =============================================================================
# REFERTI
# =============================================================================

REPORTS = [
    {"document_id": "R1", "provider": "LAB & CO", "document_type": "Esami", "document_date": "20300101"},
    {"document_id": "R2", "provider": "OSP", "document_type": "RX", "document_date": "20300102"},
]


class ReportsTests(BotTestCase):
    async def _configure(self, result):
        with mock.patch.object(bot_handlers, "download_reports", return_value=result):
            await self.send(USER, "📊 Configura Monitoraggio Referti")
            await self.send(USER, CF)
            await self.send(USER, "ABCDE12345")

    async def test_wrong_password_not_saved(self):
        await self._configure(None)
        self.assertIn("Non è stato possibile verificare", self.tg.last_text())
        self.assertEqual(reports_monitor.load_reports_monitoring(), [])

    async def test_configure_seeds_known_reports(self):
        await self._configure(REPORTS)
        items = reports_monitor.load_reports_monitoring()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["known_reports"], ["R1", "R2"])
        self.assertEqual(items[0]["telegram_chat_id"], USER)

    async def test_same_fiscal_code_two_users_kept_separate(self):
        reports_monitor.add_report_monitoring(CF, "PWD1", "803", ADMIN)
        reports_monitor.add_report_monitoring(CF, "PWD2", "803", USER)
        items = reports_monitor.load_reports_monitoring()
        self.assertEqual({i["telegram_chat_id"] for i in items}, {ADMIN, USER})

    async def test_manage_toggle_remove_and_permissions(self):
        item_id = reports_monitor.add_report_monitoring(CF, "PWD", "803", USER)
        await self.send(USER, "📋 Gestisci Monitoraggi Referti")
        self.assertIn(f"toggle_monitor_{item_id}", self.tg.buttons())
        await self.click(OTHER, f"remove_monitor_{item_id}")
        self.assertEqual(len(reports_monitor.load_reports_monitoring()), 1)
        await self.click(USER, f"toggle_monitor_{item_id}")
        self.assertFalse(reports_monitor.get_report_monitoring(item_id)["enabled"])
        await self.click(USER, f"remove_monitor_{item_id}")
        self.assertEqual(reports_monitor.load_reports_monitoring(), [])

    async def test_download_single_and_all(self):
        item_id = reports_monitor.add_report_monitoring(CF, "PWD", "803", USER)
        with mock.patch.object(bot_handlers, "download_reports", return_value=REPORTS), \
                mock.patch.object(bot_handlers, "download_report_document", return_value=b"%PDF"):
            await self.click(USER, f"download_reports_{item_id}")
            self.assertIn("report_all", self.tg.buttons())
            await self.click(USER, "report_0")
            self.assertIn("ancora altri referti", self.tg.last_text())
            self.assertEqual(reports_monitor.get_report_monitoring(item_id)["known_reports"], ["R1"])
            await self.click(USER, f"download_reports_{item_id}")
            await self.click(USER, "report_all")
        self.assertEqual(self.tg.methods().count("sendDocument"), 2)
        self.assertIsNone(reports_monitor.get_report_monitoring(item_id))

    async def test_check_now_only_own_monitorings(self):
        with mock.patch.object(bot_handlers, "check_new_reports", return_value=(1, 0, 0)) as check:
            await self.click(USER, "check_reports_now")
            check.assert_called_once_with(USER)
            await self.click(ADMIN, "check_reports_now")
            check.assert_called_with(None)

    async def test_check_new_reports_notifies_only_new_and_merges(self):
        item_id = reports_monitor.add_report_monitoring(CF, "PWD", "803", USER, ["R1"])
        sent = []
        with mock.patch.object(reports_monitor, "download_reports", return_value=REPORTS), \
                mock.patch.object(reports_monitor, "send_message_sync", side_effect=lambda c, t: sent.append(t) or True):
            result = reports_monitor.check_new_reports()
        self.assertEqual(result, (1, 1, 0))
        self.assertIn("RX", sent[0])
        self.assertNotIn("LAB &amp; CO", sent[0])
        self.assertEqual(sorted(reports_monitor.get_report_monitoring(item_id)["known_reports"]), ["R1", "R2"])

    async def test_failed_notification_retried_next_time(self):
        item_id = reports_monitor.add_report_monitoring(CF, "PWD", "803", USER)
        with mock.patch.object(reports_monitor, "download_reports", return_value=REPORTS), \
                mock.patch.object(reports_monitor, "send_message_sync", return_value=False):
            reports_monitor.check_new_reports()
        self.assertEqual(reports_monitor.get_report_monitoring(item_id)["known_reports"], [])


# =============================================================================
# MONITORAGGIO E PRENOTAZIONE AUTOMATICA
# =============================================================================

def avail(date, hospital="OSP A", price=10):
    return {"date": date, "hospital": {"id": hospital, "name": hospital}, "site": {"address": "Via"},
            "price": price, "diary": {"id": "D"}}


class MonitoringTests(BotTestCase):
    def _patch_api(self, availabilities):
        return [
            mock.patch.object(prescription_processor, "get_access_token", return_value=None),
            mock.patch.object(prescription_processor, "get_patient_info",
                              return_value={"content": [{"id": "P1", "teamCard": {"code": "803"}}]}),
            mock.patch.object(prescription_processor, "get_doctor_info", return_value={"id": "PR1"}),
            mock.patch.object(prescription_processor, "check_prescription", return_value={"content": True}),
            mock.patch.object(prescription_processor, "get_prescription_details",
                              return_value={"details": [{"service": {"id": "S1", "description": "VISITA <X>"}}]}),
            mock.patch.object(prescription_processor, "get_availabilities", return_value={"content": availabilities}),
            mock.patch.object(prescription_processor, "load_locations_db", return_value={}),
            mock.patch.object(prescription_processor, "save_locations_db"),
        ]

    async def test_notification_escaped_and_previous_updated(self):
        p = self.add_prescription_row()
        sent = []
        patches = self._patch_api([avail("2030-01-01T08:00:00Z", "OSP & <B>")])
        for patch in patches:
            patch.start()
        try:
            with mock.patch.object(prescription_processor, "send_message_sync",
                                   side_effect=lambda chat, text, reply_markup=None: sent.append((text, reply_markup)) or True):
                previous = {}
                ok, name = prescription_processor.process_prescription(p, previous)
        finally:
            for patch in patches:
                patch.stop()
        self.assertTrue(ok)
        self.assertEqual(name, "VISITA <X>")
        self.assertIn("OSP &amp; &lt;B&gt;", sent[0][0])
        self.assertIn("quickbook_", json.dumps(sent[0][1]))
        self.assertIn(f"{CF}_{NRE}", previous)
        self.assertEqual(data_utils.get_prescription(CF, NRE)["description"], "VISITA <X>")

    async def test_auto_book_saved_before_notifications(self):
        p = self.add_prescription_row(auto_book_enabled=True)
        patches = self._patch_api([avail("2030-01-01T08:00:00Z")])
        for patch in patches:
            patch.start()
        try:
            with mock.patch("modules.booking_client.booking_workflow", return_value=booked()), \
                    mock.patch.object(prescription_processor, "send_message_sync", return_value=False), \
                    mock.patch.object(prescription_processor, "send_document_sync", return_value=False):
                prescription_processor.process_prescription(p, {})
        finally:
            for patch in patches:
                patch.stop()
        stored = data_utils.get_prescription(CF, NRE)
        self.assertEqual(stored["bookings"][0]["booking_id"], "BK1")
        self.assertFalse(stored["auto_book_enabled"])

    async def test_compare_availabilities_robust_to_missing_fields(self):
        current = [{"date": "2030-01-01T08:00:00Z", "hospital": None, "site": None}]
        message = prescription_processor.compare_availabilities([], current, CF, NRE, "X", "", {})
        self.assertIn("Struttura sconosciuta", message)
        config_before = {"months_limit": None}
        prescription_processor.compare_availabilities([avail("2030-01-01T08:00:00Z")],
                                                      [avail("2030-01-02T08:00:00Z")], CF, NRE, "X", "", config_before)
        self.assertEqual(config_before, {"months_limit": None})


class ApiMessagesTests(BotTestCase):
    async def test_api_message_strips_level_prefix(self):
        from modules.api_client import api_message
        self.assertEqual(api_message({"_messages": [{"text": "E - Visualizzazione non consentita - ricetta scaduta"}]}),
                         "Visualizzazione non consentita - ricetta scaduta")
        self.assertEqual(api_message({"_not_found": True, "_messages": []}), "")
        self.assertEqual(api_message(None), "")

    async def test_api_message_priority_and_encoding(self):
        from modules.api_client import api_message
        # check-prescription: codice nel campo "code"
        check = {"content": False, "_messages": [{"code": "INVALID_PRESCRIPTION_PRIORITY", "text": "A - altro"}]}
        # availabilities: codice e testo invertiti
        avail = {"_messages": [{"code": "A - altro", "text": "INVALID_PRESCRIPTION_PRIORITY"}]}
        for result in (check, avail):
            message = api_message(result)
            self.assertIn("«A - altro»", message)
            self.assertIn("ReCUP", message)
        # Sequenza reale restituita dal server: "à" codificata due volte (Ã + NBSP)
        broken = {"_messages": [{"text": "E - Tipo operazione gi\u00c3\u00a0 utilizzato. Ricetta gi\u00c3\u00a0 presa in carico"}]}
        self.assertEqual(api_message(broken), "Tipo operazione già utilizzato. Ricetta già presa in carico")

    async def test_not_bookable_status_notified_once_and_listed(self):
        self.add_prescription_row()
        sent = []
        patches = MonitoringTests._patch_api(self, [])
        patches[3] = mock.patch.object(prescription_processor, "check_prescription", return_value={
            "content": False, "_messages": [{"code": "INVALID_PRESCRIPTION_PRIORITY", "text": "A - altro"}]})
        for patch in patches:
            patch.start()
        try:
            with mock.patch.object(prescription_processor, "send_message_sync",
                                   side_effect=lambda chat, text, reply_markup=None: sent.append(text) or True):
                for _ in range(3):
                    current = data_utils.get_prescription(CF, NRE)
                    ok, message = prescription_processor.process_prescription(current, {})
        finally:
            for patch in patches:
                patch.stop()
        self.assertFalse(ok)
        self.assertEqual(len(sent), 1)
        self.assertIn("A - altro", sent[0])
        stored = data_utils.get_prescription(CF, NRE)
        self.assertIn("A - altro", stored["status_message"])
        self.assertEqual(stored["description"], "VISITA <X>")
        await self.send(USER, "📋 Lista Prescrizioni")
        self.assertIn("Non prenotabile online", self.tg.last_text())

    async def test_status_cleared_when_bookable_again(self):
        self.add_prescription_row(status_message="ricetta scaduta")
        patches = MonitoringTests._patch_api(self, [])
        for patch in patches:
            patch.start()
        try:
            prescription_processor.process_prescription(data_utils.get_prescription(CF, NRE), {})
        finally:
            for patch in patches:
                patch.stop()
        self.assertIsNone(data_utils.get_prescription(CF, NRE)["status_message"])

    async def test_add_flow_does_not_send_duplicate_status_message(self):
        with mock.patch.object(bot_handlers, "process_prescription", return_value=(False, "motivo")) as proc:
            await self.send(USER, "➕ Aggiungi Prescrizione")
            await self.send(USER, CF)
            await self.send(USER, NRE)
            await self.send(USER, "3331234567")
            await self.send(USER, "a@b.it")
            await self.click(USER, "confirm_add")
        self.assertIs(proc.call_args.args[3], False)

    async def test_expired_prescription_reason_shown(self):
        p = self.add_prescription_row()
        patches = MonitoringTests._patch_api(self, [])
        patches[3] = mock.patch.object(prescription_processor, "check_prescription", return_value={
            "_not_found": True, "_messages": [{"code": "404", "text": "E - Visualizzazione non consentita - ricetta scaduta"}]})
        for patch in patches:
            patch.start()
        try:
            ok, message = prescription_processor.process_prescription(p, {})
        finally:
            for patch in patches:
                patch.stop()
        self.assertFalse(ok)
        self.assertIn("ricetta scaduta", message)

    async def test_multi_service_prescription_notice_and_debug_dump(self):
        p = self.add_prescription_row()
        patches = MonitoringTests._patch_api(self, [avail("2030-01-01T08:00:00Z")])
        patches[4] = mock.patch.object(prescription_processor, "get_prescription_details", return_value={"details": [
            {"service": {"id": "S1", "description": "VISITA ALLERGOLOGICA"}},
            {"service": {"id": "S2", "description": "PRICK TEST <18>"}},
        ]})
        sent = []
        for patch in patches:
            patch.start()
        try:
            with mock.patch.object(prescription_processor, "send_message_sync",
                                   side_effect=lambda chat, text, reply_markup=None: sent.append(text) or True):
                prescription_processor.process_prescription(p, {})
        finally:
            for patch in patches:
                patch.stop()
        self.assertIn("contiene 2 prestazioni", sent[0])
        self.assertIn("PRICK TEST &lt;18&gt;", sent[0])
        self.assertTrue(os.path.exists(os.path.join(os.environ["DEBUG_FOLDER"], f"{NRE}_details.json")))


class ReviewFixesTests(BotTestCase):
    async def test_admin_order_survives_reload(self):
        config.authorized_users.clear()
        config.authorized_users.extend(["987654321", "1234567890", "50"])
        data_utils.save_authorized_users()
        config.authorized_users.clear()
        data_utils.load_authorized_users()
        self.assertEqual(config.authorized_users[0], "987654321")

    async def test_cancel_booking_button_works_again_after_abandoned_flow(self):
        self.add_prescription_row(bookings=[{"booking_id": "L1", "date": "2030-05-01T08:00:00Z",
                                             "hospital": "OSP", "address": "Via", "service": "VISITA"}])
        with mock.patch.object(bot_handlers, "get_user_bookings", return_value={"success": False}):
            await self.click(USER, "cancel_appointment")
            await self.send(USER, "📋 Lista Prescrizioni")  # flusso abbandonato
            await self.click(USER, "cancel_appointment")
        self.assertIn("cancel_book_0", self.tg.buttons())

    async def test_download_all_with_more_than_40_reports(self):
        item_id = reports_monitor.add_report_monitoring(CF, "PWD", "803", USER)
        many = [{"document_id": f"R{i}", "document_type": "X", "provider": "P", "document_date": "20300101"}
                for i in range(45)]
        with mock.patch.object(bot_handlers, "download_reports", return_value=many), \
                mock.patch.object(bot_handlers, "download_report_document", return_value=b"%PDF"):
            await self.click(USER, f"download_reports_{item_id}")
            self.assertEqual(len([b for b in self.tg.buttons() if b.startswith("report_") and b[7:].isdigit()]), 40)
            await self.click(USER, "report_all")
        self.assertEqual(self.tg.methods().count("sendDocument"), 45)

    async def test_legacy_monitoring_first_check_is_silent(self):
        reports_monitor._mutate(lambda items: items.append({
            "id": "legacy1", "fiscal_code": CF, "password": "P", "tscns": "8", "telegram_chat_id": USER,
            "enabled": True, "last_check": None, "known_reports": []}))
        sent = []
        with mock.patch.object(reports_monitor, "download_reports", return_value=REPORTS), \
                mock.patch.object(reports_monitor, "send_message_sync", side_effect=lambda c, t: sent.append(t) or True):
            reports_monitor.check_new_reports()
            self.assertEqual(sent, [])
            with mock.patch.object(reports_monitor, "download_reports",
                                   return_value=REPORTS + [{"document_id": "R3", "document_type": "TAC"}]):
                reports_monitor.check_new_reports()
        self.assertEqual(len(sent), 1)
        self.assertIn("TAC", sent[0])

    async def test_error_message_with_html_chars_is_delivered(self):
        self.add_prescription_row()
        with mock.patch.object(bot_handlers, "booking_workflow",
                               return_value={"success": False, "message": "Errore <404> & altro"}):
            await self.send(USER, "🏥 Prenota")
            await self.click(USER, "book_0")
        self.assertTrue(any("Errore &lt;404&gt; &amp; altro" in t for t in self.tg.texts()))

    async def test_token_redacted_in_logs(self):
        import io
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(config._RedactTokenFormatter("%(message)s"))
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, f"url https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getMe", None, None)
        handler.emit(record)
        self.assertNotIn(config.TELEGRAM_TOKEN, stream.getvalue())

    async def test_application_can_restart_after_shutdown(self):
        await self.app.start()
        await self.app.stop()
        await self.app.shutdown()
        await self.app.initialize()
        await self.send(USER, "ℹ️ Informazioni")
        self.assertIn("Informazioni sul Bot", self.tg.last_text())


class TelegramUtilsTests(unittest.TestCase):
    def test_split_message(self):
        from modules.telegram_utils import split_message
        text = "\n".join(f"<b>riga {i}</b> " + "x" * 80 for i in range(200))
        chunks = split_message(text)
        self.assertTrue(all(len(c) <= 4000 for c in chunks))
        self.assertEqual("\n".join(chunks), text)
        self.assertEqual(split_message("breve"), ["breve"])
        self.assertTrue(all(len(c) <= 4000 for c in split_message("y" * 9000)))


if __name__ == "__main__":
    unittest.main()
