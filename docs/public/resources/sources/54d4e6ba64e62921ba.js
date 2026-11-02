import $ from "jquery";
import Vue from "vue";
import {
    global,
    getOS,
    readXPath,
    addEl,
    clearEl,
    clearReady,
    handleElement,
    clearParameters,
    generateParameters,
    generateMultiParameters,
    handleDescendents,
    generateValTable,
    findRelated,
    pushToReadyList,
    readyToList,
    combineXpath,
    relatedTest,
    LANG
} from "./global.js";
import ToolKit from "./toolkit.vue";
import iframe from "./iframe.vue";
import {createNotification} from './trial.js';

//表现逻辑层的处理

if (window.location.href.indexOf("backEndAddressServiceWrapper") >= 0) {
    chrome.storage.local.set({ "parameterNum": 1 }); //重置参数索引值
    throw "serviceGrid"; //如果是服务器网页页面，则不执行工具
}

let mousemovebind = false; //如果出现元素默认绑定了mousemove事件导致匹配不到元素的时候，开启第二种模式获得元素

let toolkit = document.createElement("div");
toolkit.classList = "tooltips"; //添加样式
// @ts-ignore
// if(isInIframe()){
//     toolkit.setAttribute("id", "wrapperToolkitIframe");
// } else {
toolkit.setAttribute("id", "wrapperToolkit");
// }


let tooltips = false; //标记鼠标是否在提示框上

//右键菜单屏蔽
document.oncontextmenu = () => false;
document.addEventListener("mousemove", function(event) {
    if (mousemovebind) {
        global.tdiv.style.pointerEvents = "none";
    }

    //如果鼠标在元素框内则点击和选中失效
    let x = event.clientX;
    let y = event.clientY;
    let divx1 = toolkit.offsetLeft;
    let divy1 = toolkit.offsetTop;
    let divx2 = toolkit.offsetLeft + toolkit.offsetWidth;
    let divy2 = toolkit.offsetTop + toolkit.offsetHeight;
    if (x >= divx1 && x <= divx2 && y >= divy1 && y <= divy2) {
        tooltips = true;
        return;
    }
    //如果鼠标在ID为notification_of_easyspider内则点击和选中失效
    try {
        let notification_of_easyspider = document.getElementsByClassName("notification_of_easyspider")[0];
        let x = event.clientX;
        let y = event.clientY;
        let divx1 = notification_of_easyspider.offsetLeft;
        let divy1 = notification_of_easyspider.offsetTop;
        let divx2 = notification_of_easyspider.offsetLeft + notification_of_easyspider.offsetWidth;
        let divy2 = notification_of_easyspider.offsetTop + notification_of_easyspider.offsetHeight;
        if (y >= divy1 - 100 && y <= divy2 + 100) {
            tooltips = true;
            // console.log("notification_of_easyspider");
            return;
        }
    } catch (e) {

    }
    global.oe = document.elementFromPoint(event.x, event.y);
    // if (global.oe == global.tdiv) {
    //     return;
    // }
    tooltips = false;
    global.NowNode = global.oe;
    let te = 0;
    let exist = 0;
    let exist2 = 0;
    for (let o of global.nodeList) { 
        if (o["node"] == global.oe) {
            exist = 1; //exist记录当前鼠标悬停的元素是否在已被选中的元素中
            break;
        }
    }
    for (let o of global.nodeList) {
        if (o["node"] == global.xnode) {
            exist2 = 1; //exist2记录上一个鼠标悬停元素是否在已被选中的元素中
            break;
        }
    }
    // console.log(oe);
    // 刚开始的时候xnode是null，xnode是上一个鼠标悬停的元素，oe是当前鼠标悬停的元素，所以把xnode赋值为oe，保证第一次悬停的时候上一个元素xnode不为null
    if (global.xnode == null) {
        global.xnode = global.oe;
    }

    // 如果当前元素与上一个元素不同，则需要处理颜色变化，因为鼠标可能在同一个元素上悬停，此时不需要处理颜色变化
    if (global.xnode != global.oe) {
        if (exist2 == 0) { //如果上个元素不在数组里，改回上个元素的初始颜色
            try {
                global.xnode.style.backgroundColor = global.style; //上个元素改回原来元素的背景颜色
            } catch {
                global.xnode.style.backgroundColor = ""; //上个元素改回原来元素的背景颜色
            }
        }

        if (exist == 1) {

        } else {
            try {
                global.style = global.oe.style.backgroundColor; //记录当前元素的背景颜色，方便在鼠标移开时恢复原来的背景颜色
                global.oe.style.backgroundColor = global.defaultbgColor; //设置新元素的背景元素
            } catch {

            }
        }
        global.xnode = global.oe;
        global.div.style.display = "none";
    }
    if (mousemovebind) {
        global.tdiv.style.pointerEvents = "";
    }

});

window.addEventListener('DOMContentLoaded', () => {
    // Remove any existing beforeunload events
    window.onbeforeunload = null;

    // Override the beforeunload event with a custom function
    window.addEventListener('beforeunload', (event) => {
        // Prevent the event's default action
        event.preventDefault();

        // Remove the confirmation message
        event.returnValue = '';
    });
});

//点击没反应时候的替代方案
document.onkeydown = function(event) {
    // console.log("keydown");
    var e = event || window.event || arguments.callee.caller.arguments[0];
    if (e && e.keyCode == 113) { // 按 F2
        addEl();
    } else if (e && e.keyCode == 119) { //按F8
        clearEl();
    } else if (e && e.keyCode == 120) { //按F9
        global.NowNode.focus();
        global.NowNode.click();
        // console.log("click",global.NowNode);
    } else {
        return event.keyCode;
    }
};

//鼠标按下事件，按下左键或者右键都会选中元素，但左键通常会触发点击事件，所以让用户按下右键选中元素
document.addEventListener("mousedown", addEl);
toolkit.addEventListener("mousedown", function(e) { e.stopPropagation(); }); //但是如果鼠标在toolkit上按下，则不选中元素，所以在这里阻止事件冒泡，防止选中元素

document.body.append(toolkit);
let timer;



//生成Toolkit
function generateToolkit() {
    $(".tooltips").html(`
    <div id="realcontent"></div>
`);
    // if(isInIframe()){
    //     global.app = new Vue(iframe);
    // } else{
    global.app = new Vue(ToolKit);
    // }

    let h = $(".tooldrag").height();
    let difference = 26 - h; //获得高度值差
    if (difference > 0) {
        $(".tooldrag").css("cssText", "height:" + (26 + difference) + "px!important")
    }
    //实现提示框拖拽功能
    $('.tooldrag').mousedown(function(e) {
        // e.pageX
        var positionDiv = $(this).offset();
        var distanceX = e.pageX - positionDiv.left;
        var distanceY = e.pageY - positionDiv.top;
        //alert(distanceX)
        //alert(positionDiv.left);

        $(document).mousemove(function(e) {
            var x = e.clientX - distanceX;
            var y = e.clientY - distanceY;

            if (x < 0) {
                x = 0;
            } else if (x > window.innerWidth - $('.tooldrag').outerWidth(true)) {
                x = window.innerWidth - $('.tooldrag').outerWidth(true);
            }

            if (y < 0) {
                y = 0;
            } else if (y > window.innerHeight - $('.tooldrag').outerHeight(true)) {
                y = window.innerHeight - $('.tooldrag').outerHeight(true);
            }

            $('.tooltips').css({
                'right': window.innerWidth - x - $('.tooltips').outerWidth(true) + 'px',
                'bottom': window.innerHeight - y - $('.tooltips').outerHeight(true) + 'px',
            });
        });

        $(document).mouseup(function() {
            $(document).off('mousemove');
        });
    });
    // 拖拽右下角改变大小
    const wrapperToolkit = document.getElementById('wrapperToolkit');
    const EasySpiderResizer = document.getElementById('EasySpiderResizer');

    let mousedown = false;
    let startX, startY, startWidth, startHeight;


    EasySpiderResizer.addEventListener('mousedown', e => {
        mousedown = true;
        startX = e.clientX;
        startY = e.clientY;
        startWidth = wrapperToolkit.offsetWidth;
        startHeight = wrapperToolkit.offsetHeight;
        e.preventDefault();
    });

    window.addEventListener('mouseup', e => {
        // when the mouse is released, stop resizing
        mousedown = false;
    });
    timer = setInterval(function() { //时刻监测相应元素是否存在(防止出现如百度一样元素消失重写body的情况)，如果不存在，添加进来
        if (document.body != null && document.getElementsByClassName("tooltips").length == 0) {
            this.clearInterval(); //先取消原来的计时器，再设置新的计时器
            document.body.append(global.div); //默认如果toolkit不存在则div和tdiv也不存在
            document.body.append(global.tdiv);
            document.body.append(toolkit);
            generateToolkit();
        }
    }, 3000);
}
//Vue元素
generateToolkit();

function closeToolkit() {
    toolkit.style.display = "none"; // 隐藏元素
    createNotification(LANG("EasySpider操作控制台已隐藏，可点击浏览器右上角扩展程序区域的EasySpider图标重新显示。", "EasySpider Toolkit is hidden. Click the EasySpider icon in the extension list (upper right corner) of the browser to reopen."));
}

let closeButton = document.getElementById("closeButton");
closeButton.addEventListener("click", function() {
    closeToolkit();
});
let closeButtonLeft = document.getElementById("closeButtonLeft");
closeButtonLeft.addEventListener("click", function() {
    closeToolkit();
});
