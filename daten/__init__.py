"""Datenhaltung von Balu's Training, nach Themen aufgeteilt.

Jedes Modul kennt nur SQLite und seine eigenen Tabellen (plus wenige Nachbarn, siehe
Importe). Von aussen benutzt man weiter `import db`: db.py ist die Fassade und
reicht alle Funktionen hier durch.
"""
