# iget - Image Get

Search Google Images and download the first N results.

## Installation

 1. Clone the repo.
    ```
    git clone https://github.com/lcordier/iget.git
    ```
 2. Install requirements.
    ```
    python3 -m pip install -r requirements.txt
    ```
 3. Download latest Chrome browser.
    [https://www.google.com/chrome/](https://www.google.com/chrome/)
 4. Download matching Sellenium Chrome Webdriver.
    [https://chromedriver.chromium.org/downloads/](https://chromedriver.chromium.org/downloads/)
 5. Install the Webdriver into your PATH.


## Known Issues

Some (most) websites block SVG downloads, possibly on `User-Agent` or `Referer`
headers.

## License

Distributed under the MIT License. See `LICENSE` for more information.


## Acknowledgements

 * [Image-Downloader](https://github.com/sczhengyabin/Image-Downloader)
 * [google-images-download](https://github.com/hardikvasa/google-images-download/)
