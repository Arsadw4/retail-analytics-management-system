(function() {
    const input=document.getElementById('globalSearchInput');
    const box=document.getElementById('globalSearchResults');
    const search=document.getElementById('globalSearch');
    let timer;
    function esc(v) {
        return String(v??'').replace(/[&<>'"]/g,c=>( {
            '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'
        }
        [c]));
    }
    function render(data,q) {
        if(!q) {
            box?.classList.remove('show');
            if(box)box.innerHTML='';
            return;
        }
        const groups=[['Records',data.records||[]],['Pages',data.pages||[]],['Actions',data.actions||[]]];
        const html=groups.filter(g=>g[1].length).map(g=>`<div class="ra-result-head">${g[0]}</div>`+g[1].map(r=>`<a class="ra-result" href="${esc(r.url)}"><span class="ra-result-icon">${esc(r.icon||'⌕')}</span><div class="ra-result-main"><strong>${esc(r.title)}</strong><small>${esc(r.meta||g[0])}</small></div><b>›</b></a>`).join('')).join('');
        if(box) {
            box.innerHTML=html||`<div class="ra-empty">No results for “${esc(q)}”<br><small>Try a product, customer, employee, supplier, sale, PO, GRN, report or feature.</small></div>`;
            box.classList.add('show');
        }
    }
    async function doSearch(q) {
        if(!q.trim()) {
            render( {
            },'');
            return;
        }
        try {
            const res=await fetch(`/admin/global-search?q=${encodeURIComponent(q.trim())}`, {
                headers: {
                    'X-Requested-With':'XMLHttpRequest'
                }
            });
            if(!res.ok)throw new Error();
            render(await res.json(),q.trim());
        } catch(e) {
            render( {
                pages:[],records:[],actions:[]
            },q.trim());
        }
    }
    input?.addEventListener('input',()=> {
        clearTimeout(timer);
        timer=setTimeout(()=>doSearch(input.value),180)
    });
    document.addEventListener('click',e=> {
        if(!search?.contains(e.target))box?.classList.remove('show');
        if(!e.target.closest('.ra-notify-wrap'))document.getElementById('notifyMenu')?.classList.remove('show');
    });
    document.addEventListener('keydown',e=> {
        if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k') {
            e.preventDefault();
            input?.focus();
            input?.select();
        }
        if(e.key==='Escape') {
            box?.classList.remove('show');
            document.getElementById('notifyMenu')?.classList.remove('show');
        }
    });
    const modal=document.getElementById('quickModal');
    document.getElementById('quickAction')?.addEventListener('click',()=>modal?.classList.add('show'));
    document.getElementById('modalClose')?.addEventListener('click',()=>modal?.classList.remove('show'));
    modal?.addEventListener('click',e=> {
        if(e.target===modal)modal.classList.remove('show');
    });
    const sidebar=document.getElementById('sidebar');
    const scrollKey='ra_sidebar_scroll';
    const saveSidebarScroll=()=> {
        if(sidebar)sessionStorage.setItem(scrollKey,String(sidebar.scrollTop));
    };
    const restoreSidebarScroll=()=> {
        if(!sidebar)return;
        const top=parseInt(sessionStorage.getItem(scrollKey)||'0',10);
        requestAnimationFrame(()=>requestAnimationFrame(()=> {
            sidebar.scrollTop=Number.isFinite(top)?top:0;
        }));
    };
    document.getElementById('mobileMenu')?.addEventListener('click',()=>sidebar?.classList.toggle('open'));
    restoreSidebarScroll();
    const path=location.pathname.replace(/\/$/,'');
    document.querySelectorAll('.ra-nav-item').forEach(a=> {
        const href=(a.getAttribute('href')||'').replace(/\/$/,'');
        if(href===path)a.classList.add('active');
        a.addEventListener('click',()=> {
            saveSidebarScroll();
            sidebar?.classList.remove('open');
        });
    });
    sidebar?.addEventListener('scroll',saveSidebarScroll, {
        passive:true
    });
    window.addEventListener('pagehide',saveSidebarScroll);
    const notifyButton=document.getElementById('notifyButton');
    const notifyMenu=document.getElementById('notifyMenu');
    const notifyItems=document.getElementById('notifyItems');
    const notifyCount=document.getElementById('notifyCount');
    if(notifyButton&&notifyMenu&&notifyItems) {
        let loaded=false;
        function esc2(v) {
            return String(v??'').replace(/[&<>'"]/g,c=>( {
                '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'
            }
            [c]));
        }
        async function load() {
            if(loaded)return;
            try {
                const res=await fetch('/admin/notifications', {
                    headers: {
                        'X-Requested-With':'XMLHttpRequest'
                    }
                });
                if(!res.ok)throw new Error();
                const data=await res.json();
                const list=data.notifications||[];
                if(data.count) {
                    notifyCount.hidden=false;
                    notifyCount.textContent=data.count>99?'99+':String(data.count);
                }else notifyCount.hidden=true;
                notifyItems.innerHTML=list.length?list.map(n=>`<a class="ra-notify-item" href="${esc2(n.url)}"><span class="ra-notify-dot"></span><div><strong>${esc2(n.title)}</strong><small>${esc2(n.meta||'Open details')}</small></div></a>`).join(''):'<div class="ra-empty">No live notifications right now.</div>';
                loaded=true;
            } catch(_) {
                notifyItems.innerHTML='<div class="ra-empty">Live notifications are unavailable right now.</div>';
            }
        }
        notifyButton.addEventListener('click',e=> {
            e.stopPropagation();
            notifyMenu.classList.toggle('show');
            box?.classList.remove('show');
            if(notifyMenu.classList.contains('show'))load();
        });
    }
    const profileButton=document.getElementById('profileButton');
    const profileMenu=document.getElementById('profileMenu');
    if(profileButton&&profileMenu) {
        profileButton.addEventListener('click',e=> {
            e.stopPropagation();
            const open=profileMenu.classList.toggle('show');
            profileButton.setAttribute('aria-expanded',open?'true':'false');
        });
        document.addEventListener('click',e=> {
            if(!profileMenu.contains(e.target)&&e.target!==profileButton) {
                profileMenu.classList.remove('show');
                profileButton.setAttribute('aria-expanded','false');
            }
        });
        document.addEventListener('keydown',e=> {
            if(e.key==='Escape') {
                profileMenu.classList.remove('show');
                profileButton.setAttribute('aria-expanded','false');
            }
        });
    }
})();
