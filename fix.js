s.links.forEach(l => {
  const row = document.createElement("div");
  row.style.display = "flex";
  row.style.alignItems = "center";
  row.style.justifyContent = "space-between";
  row.style.margin = "6px 0";

  row.innerHTML = `
    <a href="${l.url}" target="_blank" style="flex:1; text-decoration:none;">
      ${l.title}
    </a>
    <button onclick="deleteLink(${l.id})" style="
      margin-left:10px;
      padding:2px 6px;
      font-size:12px;
      background:#ff4d4d;
      color:white;
      border:none;
      border-radius:4px;
      cursor:pointer;
    ">✕</button>
  `;

  linksDiv.appendChild(row);
});
