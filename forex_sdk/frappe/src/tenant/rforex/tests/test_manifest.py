# Copyright (c) 2026 RokctAI
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
# For license information, please see license.txt

"""The manifest agrees with the code it points at, pinned standalone
(no frappe, no site — `python -m unittest`).

Whitelisted-method targets are `{app_name}`-templated strings that only
resolve inside a composed app, which means a typo in one is invisible until
deployment — the endpoint simply 404s on a live site. Parsing the api
modules with `ast` (no import, so no frappe needed) catches it here instead.

Also pins the two rules that are easy to half-apply: every DocType directory
appears in `fixtures` (a DocType missing from fixtures is not installed),
and no api module returns a broker secret.
"""

import ast
import json
import os
import unittest

_HERE = os.path.dirname(__file__)
_FRAPPE_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_API_DIR = os.path.abspath(os.path.join(_HERE, "..", "api"))
_DOCTYPE_DIR = os.path.join(_FRAPPE_ROOT, "src", "tenant", "doctype")

with open(os.path.join(_FRAPPE_ROOT, "manifest.json")) as handle:
    MANIFEST = json.load(handle)

WHITELISTED = MANIFEST["app_type"]["tenant"]["hooks"]["whitelisted_methods"]

# The installed layout: `src/tenant/rforex/` lands at
# `{app_name}/rforex/tenant/rforex/` — the persona segment plus the doubled
# module segment every target carries.
TARGET_PREFIX = "{app_name}.rforex.tenant.rforex.api."
ALIAS_PREFIX = "{app_name}.api.forex."


def _module_functions(path):
    """Top-level function names in a python file, without importing it."""
    with open(path) as handle:
        tree = ast.parse(handle.read())
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _whitelisted_functions(path):
    """Top-level functions carrying a @frappe.whitelist() decorator."""
    with open(path) as handle:
        tree = ast.parse(handle.read())
    found = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            call = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(call, ast.Attribute) and call.attr == "whitelist":
                found.add(node.name)
    return found


class TestManifestShape(unittest.TestCase):
    def test_module_name_carries_the_r_prefix(self):
        self.assertEqual(MANIFEST["name"], "rforex")

    def test_no_target_hardcodes_the_app_or_module_name(self):
        for alias, target in WHITELISTED.items():
            self.assertTrue(alias.startswith(ALIAS_PREFIX), alias)
            self.assertTrue(target.startswith(TARGET_PREFIX), target)


class TestWhitelistedMethodsResolve(unittest.TestCase):
    def test_every_target_names_a_real_module_and_function(self):
        for alias, target in WHITELISTED.items():
            tail = target[len(TARGET_PREFIX):]
            module_name, _, func_name = tail.rpartition(".")
            path = os.path.join(_API_DIR, module_name + ".py")
            self.assertTrue(os.path.isfile(path), "{0} -> missing {1}".format(alias, path))
            self.assertIn(
                func_name,
                _module_functions(path),
                "{0} -> {1} is not defined in {2}.py".format(alias, func_name, module_name),
            )

    def test_every_target_function_is_actually_whitelisted(self):
        # A manifest entry pointing at an undecorated function produces an
        # endpoint that exists in the routing table and refuses every call.
        for alias, target in WHITELISTED.items():
            tail = target[len(TARGET_PREFIX):]
            module_name, _, func_name = tail.rpartition(".")
            path = os.path.join(_API_DIR, module_name + ".py")
            self.assertIn(
                func_name,
                _whitelisted_functions(path),
                "{0} -> {1} lacks @frappe.whitelist()".format(alias, func_name),
            )

    def test_every_whitelisted_function_is_exposed_in_the_manifest(self):
        # The other direction: a decorated function nobody can reach is
        # either a missing manifest line or dead code.
        targets = set(WHITELISTED.values())
        for filename in sorted(os.listdir(_API_DIR)):
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
            module_name = filename[:-3]
            for func_name in _whitelisted_functions(os.path.join(_API_DIR, filename)):
                self.assertIn(
                    "{0}{1}.{2}".format(TARGET_PREFIX, module_name, func_name),
                    targets,
                    "{0}.{1} is whitelisted but not in the manifest".format(
                        module_name, func_name
                    ),
                )

    def test_aliases_are_unique(self):
        self.assertEqual(len(set(WHITELISTED)), len(WHITELISTED))


class TestFixtures(unittest.TestCase):
    def _fixture_doctypes(self):
        for fixture in MANIFEST["app_type"]["tenant"]["hooks"]["fixtures"]:
            if fixture.get("dt") == "DocType":
                for condition in fixture["filters"]:
                    if condition[0] == "name" and condition[1] == "in":
                        return set(condition[2])
        return set()

    def test_every_doctype_directory_is_declared_as_a_fixture(self):
        # A DocType absent from fixtures does not get installed, and the
        # failure surfaces as a missing table at runtime.
        on_disk = {
            name
            for name in os.listdir(_DOCTYPE_DIR)
            if os.path.isdir(os.path.join(_DOCTYPE_DIR, name))
        }
        declared = self._fixture_doctypes()
        declared_dirs = {name.lower().replace(" ", "_") for name in declared}
        self.assertEqual(on_disk, declared_dirs)

    def test_every_fixture_has_a_json_and_a_controller(self):
        for name in self._fixture_doctypes():
            folder = name.lower().replace(" ", "_")
            base = os.path.join(_DOCTYPE_DIR, folder)
            for suffix in (".json", ".py"):
                self.assertTrue(
                    os.path.isfile(os.path.join(base, folder + suffix)),
                    "{0}: missing {1}{2}".format(name, folder, suffix),
                )
            self.assertTrue(os.path.isfile(os.path.join(base, "__init__.py")), name)


class TestDoctypeConventions(unittest.TestCase):
    def _load(self, folder):
        path = os.path.join(_DOCTYPE_DIR, folder, folder + ".json")
        with open(path) as handle:
            return json.load(handle)

    def _folders(self):
        return sorted(
            name
            for name in os.listdir(_DOCTYPE_DIR)
            if os.path.isdir(os.path.join(_DOCTYPE_DIR, name))
        )

    def test_module_is_the_placeholder_not_a_hardcoded_name(self):
        for folder in self._folders():
            self.assertEqual(self._load(folder)["module"], "{module_name}", folder)

    def test_engine_and_autoname_follow_the_house_convention(self):
        for folder in self._folders():
            doc = self._load(folder)
            self.assertEqual(doc["engine"], "InnoDB", folder)
            self.assertEqual(doc["autoname"], "hash", folder)

    def test_system_manager_has_full_crud_everywhere(self):
        for folder in self._folders():
            perms = self._load(folder)["permissions"]
            base = [
                p
                for p in perms
                if p["role"] == "System Manager" and not p.get("permlevel")
            ]
            self.assertEqual(len(base), 1, folder)
            for right in ("read", "create", "write", "delete"):
                self.assertEqual(base[0].get(right), 1, "{0}: {1}".format(folder, right))

    def test_user_owned_rows_grant_if_owner_read(self):
        # Rows with a `user` Link are the user's own and must be readable by
        # them. Catalog rows (Forex Strategy / Version) are not user-owned
        # and are excluded deliberately — the Version spec is the product,
        # and giving `All` read there would route around the entitlement
        # gate in api/strategy.get_strategy.
        for folder in self._folders():
            doc = self._load(folder)
            fieldnames = {f["fieldname"] for f in doc["fields"]}
            if "user" not in fieldnames:
                continue
            owner_perms = [
                p for p in doc["permissions"] if p["role"] == "All" and p.get("if_owner")
            ]
            self.assertEqual(len(owner_perms), 1, folder)
            self.assertEqual(owner_perms[0].get("read"), 1, folder)

    def test_the_strategy_version_spec_is_not_readable_below_system_manager(self):
        doc = self._load("forex_strategy_version")
        self.assertEqual({p["role"] for p in doc["permissions"]}, {"System Manager"})

    def test_broker_tokens_are_password_fields_at_a_raised_permlevel(self):
        doc = self._load("forex_broker_credential")
        fields = {f["fieldname"]: f for f in doc["fields"]}
        for name in ("access_token", "refresh_token"):
            # Plain `Data` is the Saved Card precedent this deliberately
            # does not repeat.
            self.assertEqual(fields[name]["fieldtype"], "Password", name)
            self.assertEqual(fields[name].get("permlevel"), 1, name)

    def test_every_monetary_amount_sits_next_to_a_currency_code(self):
        # Nothing upstream persists this and it cannot be recovered later.
        for folder in self._folders():
            doc = self._load(folder)
            fieldnames = {f["fieldname"] for f in doc["fields"]}
            if "amount" in fieldnames:
                self.assertIn("currency", fieldnames, folder)


class TestNoSecretLeaks(unittest.TestCase):
    def test_no_api_module_returns_a_token_field(self):
        # A crude but load-bearing check: the string 'access_token' or
        # 'refresh_token' must never appear inside a dict literal that an
        # api function returns. Checked structurally rather than by grep so
        # that a helper returning a token is caught too.
        for filename in sorted(os.listdir(_API_DIR)):
            if not filename.endswith(".py"):
                continue
            with open(os.path.join(_API_DIR, filename)) as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Return) or node.value is None:
                    continue
                for inner in ast.walk(node.value):
                    if isinstance(inner, ast.Constant) and inner.value in (
                        "access_token",
                        "refresh_token",
                    ):
                        self.fail(
                            "{0}: a return value names {1!r}".format(
                                filename, inner.value
                            )
                        )


if __name__ == "__main__":
    unittest.main()
