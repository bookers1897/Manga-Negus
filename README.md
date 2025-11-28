# Manga-Negus
A native manga downloader and library manager for iOS Code App. Run a local Python server to search MangaDex, track reading progress, and bulk-download chapters as .cbz files directly to your device storage. No PC or Jailbreak required.

# 👑 MangaNegus

**MangaNegus** is a robust, self-hosted manga downloader and library manager built specifically for the **iOS Code App**.

It functions as a local web server on your iPad or iPhone, providing a desktop-class interface to search, track, and bulk-download manga chapters from MangaDex directly to your device's file system.

![MangaNegus Interface](https://via.placeholder.com/800x400?text=MangaNegus+Interface+Preview)
*(Replace this link with a real screenshot of your app running on iPad)*

## ✨ Features

* **📱 Native iOS Compatibility:** Optimized to run within the strict constraints of the [Code App](https://thebaselab.com/code/) (Pure Python, no subprocesses).
* **🔍 MangaDex Integration:** Fast, direct searching of the MangaDex database.
* **📚 Complete Library System:** Organize your collection with **Reading**, **Want to Read**, and **Completed** shelves.
* **⬇️ Smart Bulk Downloader:** Download single chapters, specific ranges, or "Download All" in the background without freezing the UI.
* **📂 Auto-CBZ:** Automatically packages downloaded images into `.cbz` files, ready for import into readers like Panels or Chunky.
* **🎛️ Live Console:** Built-in, draggable, and resizable system log panel to monitor download progress in real-time.
* **⚡ Non-Blocking Architecture:** Uses Python threading to handle downloads while you continue browsing.

## 🛠️ Prerequisites

You need the **Code App** installed on your iOS device.
* [App Store Link](https://apps.apple.com/us/app/code-app/id1512938504)

## 🚀 Installation

1.  Open **Code App** on your iOS device.
2.  Open the terminal and create a new folder named `MangaNegus`.
3.  Clone this repository or paste the files manually.
4.  **Critical:** Install the dependencies using these specific versions (required for iOS compatibility):

```bash
pip install markupsafe==2.1.3
pip install werkzeug==3.0.1
pip install flask==3.0.0
pip install requests
pip install charset-normalizer
