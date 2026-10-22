/* "Closest to me" for the home page's this-week list.
 *
 * Runs in the visitor's browser and nowhere else. Nothing happens until the
 * visitor presses the button. Then the browser asks for the device's
 * location, this script reads the static file assets/water-coords.json
 * (a plain GET that carries no location), works out the distance to each
 * water on the page, and builds a sorted list. The location is held in
 * memory for that one calculation: it is not sent anywhere, not put in a URL,
 * not stored, and not given to analytics. Without JavaScript the section
 * stays hidden and the page is the list it always was.
 */
(function (root) {
  "use strict";

  var EARTH_RADIUS_MILES = 3958.8;

  // Straight-line (great-circle) distance in miles.
  function milesBetween(lat1, lon1, lat2, lon2) {
    var rad = Math.PI / 180;
    var dLat = (lat2 - lat1) * rad;
    var dLon = (lon2 - lon1) * rad;
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * rad) * Math.cos(lat2 * rad) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * EARTH_RADIUS_MILES * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  // rows: [{slug, ...}]. coords: {slug: [lat, lon, "w" | "s"]}.
  // Returns {placed: rows with a distance, nearest first; unplaced: the rest}.
  // A water listed twice (two regions) is counted once.
  function sortByDistance(origin, rows, coords) {
    var seen = {};
    var placed = [];
    var unplaced = [];
    rows.forEach(function (row) {
      if (seen.hasOwnProperty(row.slug)) return;
      seen[row.slug] = true;
      var c = Object.prototype.hasOwnProperty.call(coords, row.slug)
        ? coords[row.slug]
        : null;
      if (!c) {
        unplaced.push(row);
        return;
      }
      var copy = {};
      Object.keys(row).forEach(function (k) { copy[k] = row[k]; });
      copy.miles = milesBetween(origin.lat, origin.lon, c[0], c[1]);
      copy.approximate = c[2] === "s";
      placed.push(copy);
    });
    placed.sort(function (a, b) {
      return a.miles - b.miles || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
    });
    return { placed: placed, unplaced: unplaced };
  }

  function milesLabel(miles) {
    if (miles < 1) return "under 1 mile";
    var n = Math.round(miles);
    return "about " + n + (n === 1 ? " mile" : " miles");
  }

  var api = { milesBetween: milesBetween, sortByDistance: sortByDistance, milesLabel: milesLabel };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!root || !root.document) return;

  var doc = root.document;
  var nav = root.navigator;
  var section = doc.getElementById("closest");
  var button = doc.getElementById("closest-button");
  var status = doc.getElementById("closest-status");
  var result = doc.getElementById("closest-result");
  if (!section || !button || !status || !result) return;
  // No geolocation or no fetch in this browser: leave the section hidden.
  if (!nav || !nav.geolocation || typeof root.fetch !== "function") return;
  section.hidden = false;

  function say(message) { status.textContent = message; }

  function readRows() {
    var rows = [];
    var trs = doc.querySelectorAll("tr[data-slug]");
    for (var i = 0; i < trs.length; i++) {
      var tr = trs[i];
      var cells = tr.querySelectorAll("td");
      var link = cells[0] ? cells[0].querySelector("a") : null;
      if (!link) continue;
      rows.push({
        slug: tr.getAttribute("data-slug"),
        name: link.textContent,
        href: link.getAttribute("href"),
        county: cells[1] ? cells[1].textContent : "",
        species: cells[2] ? cells[2].textContent : ""
      });
    }
    return rows;
  }

  function show(sorted) {
    while (result.firstChild) result.removeChild(result.firstChild);
    var list = doc.createElement("ol");
    list.className = "closest-list";
    sorted.placed.forEach(function (row) {
      var li = doc.createElement("li");
      var a = doc.createElement("a");
      a.setAttribute("href", row.href);
      a.textContent = row.name;
      li.appendChild(a);
      var detail = row.county ? ", " + row.county + " County" : "";
      detail += row.species ? ", " + row.species : "";
      detail += ": " + milesLabel(row.miles) + (row.approximate ? " (approximate)" : "");
      li.appendChild(doc.createTextNode(detail));
      list.appendChild(li);
    });
    result.appendChild(list);
    if (sorted.unplaced.length) {
      var p = doc.createElement("p");
      p.className = "muted";
      p.textContent =
        sorted.unplaced.length +
        (sorted.unplaced.length === 1 ? " water" : " waters") +
        " on this week's schedule " +
        (sorted.unplaced.length === 1 ? "has" : "have") +
        " no location on file and " +
        (sorted.unplaced.length === 1 ? "is" : "are") +
        " not in this list. " +
        (sorted.unplaced.length === 1 ? "It is" : "They are") +
        " in the lists below.";
      result.appendChild(p);
    }
  }

  function onPosition(position) {
    var origin = { lat: position.coords.latitude, lon: position.coords.longitude };
    var rows = readRows();
    root
      .fetch(section.getAttribute("data-coords"), { credentials: "omit" })
      .then(function (response) {
        if (!response.ok) throw new Error("coordinates file " + response.status);
        return response.json();
      })
      .then(function (file) {
        var sorted = sortByDistance(origin, rows, file.waters);
        if (!sorted.placed.length) {
          say("No water on this week's schedule has a location on file, so the list is unchanged.");
          return;
        }
        show(sorted);
        say("Sorted by straight-line distance from where your browser says you are. Nothing about your location was sent.");
      })
      .catch(function () {
        say("The list of locations could not be loaded, so the list is unchanged.");
      })
      .then(function () { button.disabled = false; });
  }

  function onFailure(error) {
    button.disabled = false;
    if (error && error.code === 1) {
      say("Your browser did not share your location, so the list is unchanged.");
    } else {
      say("Your location could not be found, so the list is unchanged.");
    }
  }

  button.addEventListener("click", function () {
    button.disabled = true;
    say("Waiting for your browser to ask about your location.");
    nav.geolocation.getCurrentPosition(onPosition, onFailure, { timeout: 20000 });
  });
})(typeof window !== "undefined" ? window : null);
