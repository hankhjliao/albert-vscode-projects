# -*- coding: utf-8 -*-

import os
import json
import unicodedata

from typing import *
from albert import *

md_iid = "0.5"
md_version = "0.1"
md_name = "Open VS Code Projects"
md_description = "List and open VS Code projects and recently opened directories."
md_license = "MIT"
md_url = "https://github.com/hankliao87/albert-vscode-projects"
md_maintainers = "@hankliao87"
md_bin_dependencies = ["sqlite3"]

trigger = "vc "

import sqlite3

default_icon = [os.path.dirname(__file__) + "/vscode.svg"]

HOME_DIR = os.environ["HOME"]
EXEC = '/usr/bin/code'
VARIANT = 'Code'

# Recent paths for VS Code versions after 1.64
# :uri https://code.visualstudio.com/updates/v1_64
# Path to the VS Code database file where recent paths can be queried
STORAGE_DB_XDG_CONFIG_DIR = os.path.join(
    HOME_DIR,
    ".config", VARIANT, "User/globalStorage/state.vscdb"
)
# Recent paths for VS Code versions before 1.64
# Path to the VS Code storage json file where recent paths can be queried
STORAGE_DIR_XDG_CONFIG_DIRS = [
    os.path.join(HOME_DIR, ".config", VARIANT, "storage.json"),
    os.path.join(HOME_DIR, ".config", VARIANT,
                 "User/globalStorage/storage.json"),
]

# Path to the Project Manager plugin configuration
PROJECT_MANAGER_XDG_CONFIG_DIR = os.path.join(
    HOME_DIR,
    ".config", VARIANT, "User/globalStorage/alefragnani.project-manager/projects.json"
)


def normalizeString(input: str) -> str:
    """
    Normalizes search string (accents and whatnot)
    """
    return ''.join(c for c in unicodedata.normalize('NFD', input)
                   if unicodedata.category(c) != 'Mn').lower()


def addProjectEntry(uri: str, index=0, tags=[]) -> None:
    """
    Helper function to add project entry from various sources
    """
    global projects
    global queryString

    # For remote machine ("vscode-remote://ssh-remote+<hostname>/...")
    if uri.startswith('vscode-remote://ssh-remote%2B'):
        # Remove uri string
        path = uri.replace('vscode-remote://ssh-remote%2B', '', 1)

        # Split hostname and file path
        hostname, path = path.split('/', 1)
        path = '/' + path

        descrip = f'[{hostname}] {path}'
        cmd = ['--remote', f'ssh-remote+{hostname}', path]

    # For local directory ("file://..." or "/...")
    elif uri.startswith('file://') or uri.startswith('/'):
        # Remove uri string
        path = uri.replace('file://', '', 1)

        # Check directory exist
        if not os.path.exists(path):
            return

        descrip = path
        cmd = [path]

    else:
        return

    name = path.split("/")[-1]

    # Normalize the directory in which the project resides
    nameNormalized = normalizeString(name)
    descripNormalized = normalizeString(descrip)
    tagsNormalized = normalizeString(' '.join(tags))

    # Compare the normalized dir with user query
    queryList = [nameNormalized, descripNormalized, tagsNormalized]
    if any([i.find(queryString) != -1 for i in queryList]):
        projects[descrip] = {
            'name': name,
            'descrip': descrip,
            'cmd': cmd,
            'index': '{0:04d}'.format(index),  # Zeropad for easy sorting
        }


class Plugin(QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self) -> str:
        return md_description

    def synopsis(self) -> str:
        return "<filter>"

    def defaultTrigger(self) -> str:
        return trigger

    def handleQuery(self, query: str) -> None:
        # Create projects dictionary to store projects by paths
        global projects
        projects = {}

        # Normalize user query
        global queryString
        queryString = normalizeString(query.string)

        # Use incremental index for sorting which will keep the projects
        # sorted from least recent to oldest one
        sortIndex = 1

        # Recent paths for Visual Studio Code versions after 1.64
        if os.path.exists(STORAGE_DB_XDG_CONFIG_DIR):
            con = sqlite3.connect(STORAGE_DB_XDG_CONFIG_DIR)
            cur = con.cursor()
            cur.execute(
                'SELECT value FROM ItemTable WHERE key = "history.recentlyOpenedPathsList"')
            json_code, = cur.fetchone()
            paths_list = json.loads(json_code)

            for item in paths_list['entries']:
                uri = item.get('folderUri', '')

                # Add project entry
                addProjectEntry(uri=uri, index=sortIndex)
                sortIndex += 1

        # Recent paths for Visual Studio Code versions before 1.64
        else:
            for storageFile in STORAGE_DIR_XDG_CONFIG_DIRS:
                if os.path.exists(storageFile):
                    with open(storageFile) as configFile:
                        # Load the storage json
                        storageConfig = json.loads(configFile.read())

                        # These are all the menu items in "File" dropdown
                        for menuItem in storageConfig.get('lastKnownMenubarData', {}).get('menus', {}).get('File', {}).get('items', []):
                            if menuItem.get('label', '') != 'Open &&Recent':
                                continue

                            # Get the item in the "Open &&Recent"
                            for submenuItem in menuItem.get('submenu', {}).get('items', []):
                                # Check of submenu item with id "openRecentFolder" and make sure it is enabled
                                if (
                                    submenuItem.get('id', '') != "openRecentFolder"
                                    or submenuItem.get('enabled', False) == False
                                ):
                                    continue

                                uri = submenuItem.get(
                                    'uri', {}).get('external', '')
                                if uri == '':
                                    uri = submenuItem.get(
                                        'uri', {}).get('path', '')

                                # Add project entry
                                addProjectEntry(uri=uri, index=sortIndex)
                                sortIndex += 1

        # Check whether the Project Manager config file exists
        if os.path.exists(PROJECT_MANAGER_XDG_CONFIG_DIR):
            with open(PROJECT_MANAGER_XDG_CONFIG_DIR) as configFile:
                configuredProjects = json.loads(configFile.read())

                for project in configuredProjects:
                    # Make sure we have necessarry keys
                    if not project.get('enabled', False):
                        continue

                    # Grab the path to the project
                    uri = project.get('rootPath', '')

                    # Add project entry
                    addProjectEntry(
                        uri=uri, tags=project.get('tags', []))

        # Sort projects by indexes
        sorted_project_items = sorted(projects.items(), key=lambda item: "%s_%s_%s" % (
            item[1]['index'], item[1]['name'], item[1]['descrip']), reverse=False)

        # Array of Items we will return to albert launcher
        for item in sorted_project_items:
            project = item[1]
            name = project['name']
            descrip = project['descrip']
            cmd = [EXEC] + project['cmd']

            item = Item(
                id="%s" % (descrip),
                icon=default_icon,
                text=name,
                subtext=descrip,
                actions=[
                    Action(
                        id="open",
                        text="Open in VS Code",
                        callable=lambda u=cmd: runDetachedProcess(u))
                ]
            )

            query.add(item)
