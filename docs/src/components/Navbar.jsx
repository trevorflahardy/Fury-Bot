import { fb_logo, menu, close, menu_black, close_black } from '../assets';
import { navLinks } from "../constants";

import { useState, useEffect, } from 'react';
import { Link } from 'react-router-dom';


const Navbar = () => {
    const [theme, setTheme] = useState(null);
    const [toggle, setToggle] = useState(false);
    const [active, setActive] = useState("Home");

    useEffect(() => {
        if (window.matchMedia('prefers-color-scheme: dark').matches) {
            setTheme("dark");
        }
        else {
            setTheme("light");
        }
    }, []);

    useEffect(() => {
        if (theme == "dark") {
            document.documentElement.classList.add("dark");
        } else {
            document.documentElement.classList.remove("dark");
        }
    }, [theme])

    const handleThemeSwitch = () => {
        setTheme(theme == "dark" ? "light" : "dark");
    }

    return (
        <nav className="w-full flex py-6 justify-between items-center navbar">
            {/* FuryBot Logo */}
            <div className="pl-5">
                <img src={fb_logo} alt="Fury-Bot Logo" className="w-[50px] h-[50px] rounded-full drop-shadow-lg" />
            </div>


            {/* Navigation Links for desktop (hidden for mobile) */}
            <ul className="list-none sm:flex hidden justify-end items-center flex-1 space-x-5" >
                <li className="font-poppins font-normal cursor-pointer text-[16px] text-light-text dark:text-white-medium rounded-md bg-light-bg dark:bg-gray-medium shadow-lg">
                    {/* Links to the documentation */}
                    <Link to="/docs" className="px-4 py-3 flex space-x-2">Docs</Link>

                </li>


                {navLinks.map((nav, _index) => (
                    <li
                        key={nav.id}
                        className="font-poppins font-normal cursor-pointer text-[16px] text-light-text dark:text-white-medium rounded-md bg-light-bg dark:bg-gray-medium shadow-lg"
                    >
                        <button className="px-4 py-3 flex space-x-2">
                            <a href={`${nav.url}`}>{nav.title}</a>
                            {
                                nav.icon && <img src={nav.icon[theme]} className="w-[25px] h-[25px]" />
                            }
                        </button>
                    </li>
                ))}

                {/* button for theme toggling */}
                <li className="font-poppins font-normal cursor-pointer text-[16px] text-light-text dark:text-white-medium rounded-md bg-light-bg dark:bg-gray-medium shadow-lg">
                    <button className="px-4 py-3 flex space-x-12" onClick={handleThemeSwitch}>
                        Toggle Dark Mode
                    </button>
                </li>
            </ul>

            {/* Navigation Links for mobile (hidden for desktop) */}
            <div className="sm:hidden flex flex-1 justify-end items-center">
                <img
                    src={toggle ? (theme == "dark" ? close : close_black) : (theme == "dark" ? menu : menu_black)}
                    alt="menu"
                    className={`w-[28px] h-[28px] object-contain`}
                    onClick={() => setToggle(!toggle)}
                />

                <div
                    className={`${!toggle ? "hidden" : "flex"} p-6 bg-light-bg border-2 dark:border-light-bg absolute top-20 right-0 mx-4 my-2 min-w-[140px] rounded-xl sidebar`}
                >
                    <ul className="list-none flex justify-end items-start flex-1 flex-col">
                        {navLinks.map((nav, _index) => (
                            <li
                                key={nav.id}
                                className='font-poppins font-medium cursor-pointer text-[16px] text-light-text'
                                onClick={() => setActive(nav.title)}
                            >
                                <a href={`${nav.url}`}>{nav.title}</a>
                            </li>
                        ))}

                        {/* button for theme toggling */}
                        <li className="font-poppins font-medium cursor-pointer text-[16px] text-light-text">
                            <button className="" onClick={handleThemeSwitch}>
                                <a>Dark Mode</a>
                            </button>
                        </li>
                    </ul>
                </div>
            </div>


        </nav>
    )
}

export default Navbar