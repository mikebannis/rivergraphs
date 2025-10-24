from flask import Flask, request

app = Flask(__name__)
from app import views


@app.context_processor
def nav_link_processor():
    def nav_link(path, name):
        """
        Create nav link for a page. Mark as current if it is the current page.

        @param {str} path - path of the page, e.g. '/front_range'
        @param {str} name - display name of the page, e.g. 'Front Range'
        @returns {str} - <a> tag for link
        """
        active = "active" if request.path == path else ""
        aria_current = 'aria-current="page"' if request.path == path else ""
        html = f'<a class="nav-link {active}" {aria_current} href="{path}">{name}</a>'

        return html

    return {"nav_link": nav_link}
