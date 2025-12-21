(function(){
  function parseISO(s){ return new Date(s + "T00:00:00"); }
  function fmt(d){ return d.toISOString().slice(0,10); }

  function daysBetween(a,b){
    return Math.round((parseISO(b)-parseISO(a)) / (24*3600*1000));
  }

  function clearSelected(){
    document.querySelectorAll(".day.selected").forEach(el=>el.classList.remove("selected"));
  }

  function markRange(start, end){
    clearSelected();
    const startD = parseISO(start);
    const endD = parseISO(end);
    document.querySelectorAll(".day[data-date]").forEach(el=>{
      const d = parseISO(el.dataset.date);
      if(d >= startD && d < endD){
        el.classList.add("selected");
      }
    });
  }

  function init(){
    const wrap = document.querySelector(".cal-wrap");
    if(!wrap) return;

    // --- Dynamic Pricing Logic ---
    // These values must be provided by your template (e.g., listing_detail.html)
    const priceRules = JSON.parse(wrap.dataset.priceRules || "[]");
    const basePrice = parseFloat(wrap.dataset.basePrice || "0");

    function calculateTotal(startStr, endStr) {
        let current = parseISO(startStr);
        let end = parseISO(endStr);
        let total = 0;
        let nights = 0;

        while (current < end) {
            let dayPrice = basePrice;
            let dayIso = fmt(current);
            let dayOfWeek = (current.getDay() + 6) % 7; // Adjust to 0=Monday

            // Find applicable rule: specific weekday rules override general seasonal rules
            let applicableRule = priceRules.find(r => {
                const inRange = (!r.start_date || dayIso >= r.start_date) && (!r.end_date || dayIso <= r.end_date);
                const matchesWeekday = r.weekday === null || r.weekday === dayOfWeek;
                return inRange && matchesWeekday;
            });

            if (applicableRule) dayPrice = applicableRule.price_per_night;
            
            total += dayPrice;
            nights++;
            current.setDate(current.getDate() + 1);
        }
        return { total, nights };
    }

    function updatePriceDisplay(start, end) {
        const summary = document.getElementById("priceSummary");
        const nightCountEl = document.getElementById("nightCount");
        const totalPriceEl = document.getElementById("totalPrice");

        if (start && end && summary && nightCountEl && totalPriceEl) {
            const { total, nights } = calculateTotal(start, end);
            nightCountEl.innerText = nights;
            totalPriceEl.innerText = total.toFixed(0);
            summary.style.display = "block";
        } else if (summary) {
            summary.style.display = "none";
        }
    }
    // -----------------------------

    let start = null;
    let end = null;

    function setHidden(){
      const sIn = document.getElementById("startInput");
      const eIn = document.getElementById("endInput");
      const sD = document.getElementById("startDisplay");
      const eD = document.getElementById("endDisplay");
      if(sIn) sIn.value = start || "";
      if(eIn) eIn.value = end || "";
      if(sD) sD.value = start || "";
      if(eD) eD.value = end || "";
      
      // Update the price display whenever the selection changes
      updatePriceDisplay(start, end);
    }

    function isBlocked(dateStr){
      const el = document.querySelector('.day[data-date="'+dateStr+'"]');
      if(!el) return true;
      return el.classList.contains("booked");
    }

    function rangeHasBooked(s,e){
      const n = daysBetween(s,e);
      for(let i=0;i<n;i++){
        const d = new Date(parseISO(s).getTime() + i*24*3600*1000);
        const iso = fmt(d);
        const el = document.querySelector('.day[data-date="'+iso+'"]');
        if(el && el.classList.contains("booked")) return true;
      }
      return false;
    }

    wrap.addEventListener("click", (e)=>{
      const t = e.target;
      if(!t.classList || !t.classList.contains("day") || !t.dataset.date) return;
      if(t.classList.contains("disabled") || t.classList.contains("booked")) return;

      const clicked = t.dataset.date;

      if(!start || (start && end)){
        start = clicked;
        end = null;
        clearSelected();
        t.classList.add("selected");
      } else {
        if(parseISO(clicked) <= parseISO(start)){
          start = clicked;
          end = null;
          clearSelected();
          t.classList.add("selected");
        } else {
          if(rangeHasBooked(start, clicked)){
            start = clicked;
            end = null;
            clearSelected();
            t.classList.add("selected");
          } else {
            end = clicked;
            markRange(start, end);
          }
        }
      }
      setHidden();
    });

    const form = document.getElementById("bookForm");
    if(form){
      form.addEventListener("submit", (e)=>{
        if(!start || !end){
          e.preventDefault();
          alert("Please select check-in and check-out dates on the calendar.");
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();